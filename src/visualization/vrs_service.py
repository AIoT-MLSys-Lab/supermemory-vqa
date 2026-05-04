"""
VRS file processing and conversion service.

Handles conversion of VRS files to MP4 using projectaria_tools.
Uses a ThreadPoolExecutor-based task queue with configurable workers.
Subprocesses are tracked for proper cancellation support.

Reference: https://facebookresearch.github.io/projectaria_tools/docs/data_utilities/advanced_code_snippets/vrs_to_mp4

Configuration:
    VRS_CONVERSION_WORKERS: Number of worker threads (default: CPU cores / 2, min 1)
    Set in .env file or environment variable.
"""
import logging
import os
import subprocess
import json
import threading
import uuid
import multiprocessing
import signal
import tempfile
import shutil
import time
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Dict, Any, Tuple, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from flask.cli import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()
# Get number of workers from environment, default to half of CPU cores (minimum 1)
DEFAULT_WORKERS = max(1, multiprocessing.cpu_count() // 2)
VRS_CONVERSION_WORKERS = int(os.environ.get('VRS_CONVERSION_WORKERS', DEFAULT_WORKERS))

# Logging interval for queue stats in seconds
QUEUE_LOG_INTERVAL = int(os.environ.get('QUEUE_LOG_INTERVAL', 30))

logger.info("VRS conversion workers: %d (CPU cores: %d)", VRS_CONVERSION_WORKERS, multiprocessing.cpu_count())

# Event subscribers for SSE notifications
_task_event_subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
_subscriber_lock = threading.Lock()


def subscribe_to_task_events(callback: Callable[[str, Dict[str, Any]], None]):
    """Subscribe to task status change events."""
    with _subscriber_lock:
        _task_event_subscribers.append(callback)


def unsubscribe_from_task_events(callback: Callable[[str, Dict[str, Any]], None]):
    """Unsubscribe from task status change events."""
    with _subscriber_lock:
        if callback in _task_event_subscribers:
            _task_event_subscribers.remove(callback)


def _notify_task_event(event_type: str, task_data: Dict[str, Any]):
    """Notify all subscribers of a task event."""
    with _subscriber_lock:
        subscribers = list(_task_event_subscribers)
    
    for callback in subscribers:
        try:
            callback(event_type, task_data)
        except Exception as exc:
            logger.warning("Error notifying task event subscriber: %s", exc)


class ConversionStatus(Enum):
    """Status of a VRS to MP4 conversion task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ConversionTask:
    """Represents a VRS to MP4 conversion task."""
    task_id: str
    filename: str
    vrs_path: str
    output_path: str
    status: ConversionStatus = ConversionStatus.PENDING
    progress: float = 0.0
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'task_id': self.task_id,
            'filename': self.filename,
            'status': self.status.value,
            'progress': self.progress,
            'message': self.message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error': self.error
        }


PROCESS_TERMINATION_TIMEOUT_SECONDS = 5


class ConversionManager:
    """Manages background VRS to MP4 conversions using a thread pool.
    
    Uses a fixed-size ThreadPoolExecutor for conversion tasks.
    Each thread spawns a subprocess that can be terminated for cancellation.
    The number of workers is configurable via VRS_CONVERSION_WORKERS env var.
    
    Uses Server-Sent Events (SSE) for real-time status updates.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._tasks: Dict[str, ConversionTask] = {}
        self._tasks_by_filename: Dict[str, str] = {}  # filename -> task_id
        self._processes: Dict[str, subprocess.Popen] = {}  # task_id -> subprocess
        # Use RLock (reentrant lock) to allow nested locking from same thread
        self._task_lock = threading.RLock()
        
        # Create thread pool with configurable workers
        self._num_workers = VRS_CONVERSION_WORKERS
        self._executor = ThreadPoolExecutor(max_workers=self._num_workers)
        self._initialized = True
        
        # Start queue logging thread
        self._log_interval = QUEUE_LOG_INTERVAL
        self._logger_thread = threading.Thread(target=self._log_queue_stats, daemon=True)
        self._logger_thread.start()
        
        logger.info("ConversionManager initialized with %d workers", self._num_workers)
        
    def _log_queue_stats(self):
        """Periodically log queue statistics."""
        while True:
            try:
                time.sleep(self._log_interval)
                
                with self._task_lock:
                    pending = 0
                    running = 0
                    files = []
                    
                    for task in self._tasks.values():
                        if task.status == ConversionStatus.PENDING:
                            pending += 1
                        elif task.status == ConversionStatus.RUNNING:
                            running += 1
                            files.append(task.filename)
                    
                    # Only log if there's activity
                    if pending > 0 or running > 0:
                        logger.info(
                            "Queue Status: %d running (%d workers total), %d pending. Processing: %s",
                            running, self._num_workers, pending, ", ".join(files)
                        )
            except Exception as e:
                logger.error("Error in queue logger: %s", e)
                # Sleep a bit to avoid tight loop on error
                time.sleep(5)
    
    @property
    def num_workers(self) -> int:
        """Return the number of worker threads."""
        return self._num_workers
    
    def start_conversion(
        self,
        filename: str,
        vrs_path: str,
        output_path: str,
        rotate: bool = True
    ) -> ConversionTask:
        """
        Start a background VRS to MP4 conversion.
        
        Submits the task to the thread pool for execution.
        
        Args:
            filename: The VRS filename
            vrs_path: Full path to the VRS file
            output_path: Full path for output MP4
            rotate: Whether to apply rotation correction (currently ignored)
            
        Returns:
            ConversionTask object
        """
        with self._task_lock:
            # Check if already processing this file
            if filename in self._tasks_by_filename:
                existing_task_id = self._tasks_by_filename[filename]
                existing_task = self._tasks.get(existing_task_id)
                if existing_task and existing_task.status in (ConversionStatus.PENDING, ConversionStatus.RUNNING):
                    return existing_task
            
            # Create new task
            task_id = str(uuid.uuid4())
            task = ConversionTask(
                task_id=task_id,
                filename=filename,
                vrs_path=vrs_path,
                output_path=output_path,
                status=ConversionStatus.PENDING,
                message="Queued for conversion..."
            )
            
            self._tasks[task_id] = task
            self._tasks_by_filename[filename] = task_id
        
        # Notify task started
        _notify_task_event('task_started', task.to_dict())
        
        # Submit to thread pool
        self._executor.submit(self._run_conversion, task)
        
        return task
    
    def _run_conversion(self, task: ConversionTask):
        """Run the VRS to MP4 conversion in a background thread.
        
        This method runs in a thread pool worker. It spawns a subprocess
        that can be terminated if the task is cancelled.
        """
        task.status = ConversionStatus.RUNNING
        task.started_at = datetime.now()
        task.message = "Converting VRS to MP4..."
        
        logger.info("Starting conversion: %s (workers: %d)", task.filename, self._num_workers)
        
        # Create temporary directory for logs and intermediate files
        temp_dir = tempfile.mkdtemp(prefix=f"vrs_convert_{task.task_id}_")
        
        try:
            # Build the vrs_to_mp4 command
            # Use specific log folder to prevent race conditions with intermediate files (audio.wav, etc.)
            cmd = ['vrs_to_mp4', '--vrs', task.vrs_path, '--output_video', task.output_path, '--log_folder', temp_dir]
            
            # Start the subprocess
            # Set cwd=temp_dir to ensure any implicit temporary files derived from CWD
            # (implying moviepy temp_audiofile default) are isolated.
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=temp_dir
            )
            
            # Track the process for cancellation
            with self._task_lock:
                self._processes[task.task_id] = process
            
            # Wait for completion
            stdout, stderr = process.communicate()
            
            # Remove from process tracking
            with self._task_lock:
                self._processes.pop(task.task_id, None)
            
            # Check if cancelled while running
            if task.status == ConversionStatus.CANCELLED:
                logger.info("Conversion was cancelled: %s", task.filename)
                return
            
            # Check result
            if process.returncode == 0 and os.path.exists(task.output_path):
                task.status = ConversionStatus.COMPLETED
                task.progress = 100.0
                task.message = "Conversion completed successfully"
                logger.info("Conversion completed: %s", task.filename)
            else:
                task.status = ConversionStatus.FAILED
                task.error = stderr or stdout or "Unknown error"
                task.message = "Conversion failed"
                logger.error("Conversion failed for %s: %s", task.filename, task.error)
                
        except FileNotFoundError:
            task.status = ConversionStatus.FAILED
            task.error = "vrs_to_mp4 tool not found. Please install projectaria_tools."
            task.message = "Tool not found"
            logger.error("vrs_to_mp4 not found")
            
        except Exception as exc:
            # Check if cancelled
            if task.status == ConversionStatus.CANCELLED:
                logger.info("Conversion was cancelled: %s", task.filename)
                return
                
            task.status = ConversionStatus.FAILED
            task.error = str(exc)
            task.message = "Conversion error"
            logger.error("Conversion error for %s: %s", task.filename, exc)
            
        finally:
            # Clean up temp dir
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir {temp_dir}: {e}")

            # Clean up process reference
            with self._task_lock:
                self._processes.pop(task.task_id, None)
            
            task.completed_at = datetime.now()
            
            # Notify completion via SSE (unless cancelled - that's handled separately)
            if task.status != ConversionStatus.CANCELLED:
                _notify_task_event('task_completed', task.to_dict())
    
    def cancel_conversion(self, task_id: str) -> bool:
        """
        Cancel a running conversion by terminating the subprocess.
        
        Args:
            task_id: The task ID to cancel
            
        Returns:
            True if cancelled, False if not found or already completed
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning("Cancel failed: task %s not found", task_id)
                return False
            
            if task.status not in (ConversionStatus.PENDING, ConversionStatus.RUNNING):
                logger.warning("Cancel failed: task %s status is %s", task_id, task.status)
                return False
            
            # Mark as cancelled first
            task.status = ConversionStatus.CANCELLED
            task.message = "Cancelled by user"
            task.completed_at = datetime.now()
            
            # Terminate the subprocess if it's running
            process = self._processes.pop(task_id, None)
            if process:
                try:
                    logger.info("Terminating subprocess for task: %s (PID: %d)", task_id, process.pid)
                    process.terminate()
                    try:
                        process.wait(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
                        logger.info("Subprocess terminated gracefully for task: %s", task_id)
                    except subprocess.TimeoutExpired:
                        logger.warning("Subprocess did not terminate, killing: %s", task_id)
                        process.kill()
                        process.wait()
                except Exception as exc:
                    logger.warning("Error terminating subprocess for task %s: %s", task_id, exc)
            
            logger.info("Conversion cancelled: %s", task.filename)
            _notify_task_event('task_cancelled', task.to_dict())
            return True
    
    def cancel_by_filename(self, filename: str) -> bool:
        """Cancel conversion by filename."""
        with self._task_lock:
            task_id = self._tasks_by_filename.get(filename)
            if task_id:
                # Release lock before calling cancel_conversion to avoid deadlock
                pass
        
        if task_id:
            return self.cancel_conversion(task_id)
        return False
    
    def get_task(self, task_id: str) -> Optional[ConversionTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def get_task_by_filename(self, filename: str) -> Optional[ConversionTask]:
        """Get a task by filename."""
        task_id = self._tasks_by_filename.get(filename)
        if task_id:
            return self._tasks.get(task_id)
        return None
    
    def get_active_tasks(self) -> Dict[str, ConversionTask]:
        """Get all active (pending/running) tasks."""
        return {
            tid: task for tid, task in self._tasks.items()
            if task.status in (ConversionStatus.PENDING, ConversionStatus.RUNNING)
        }
    
    def get_all_tasks(self) -> Dict[str, ConversionTask]:
        """Get all tasks."""
        return dict(self._tasks)
    
    def get_processing_filenames(self) -> list:
        """Get list of filenames currently being processed (active tasks only)."""
        with self._task_lock:
            return [
                task.filename for task in self._tasks.values()
                if task.status in (ConversionStatus.PENDING, ConversionStatus.RUNNING)
            ]
    
    def is_processing(self, filename: str) -> bool:
        """Check if a file is currently being processed."""
        task = self.get_task_by_filename(filename)
        return task is not None and task.status in (ConversionStatus.PENDING, ConversionStatus.RUNNING)
    
    def cleanup_completed(self, max_age_seconds: int = 3600):
        """Remove completed/failed/cancelled tasks older than max_age."""
        now = datetime.now()
        with self._task_lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status in (ConversionStatus.COMPLETED, ConversionStatus.FAILED, ConversionStatus.CANCELLED):
                    if task.completed_at and (now - task.completed_at).total_seconds() > max_age_seconds:
                        to_remove.append(task_id)
            
            for task_id in to_remove:
                task = self._tasks.pop(task_id, None)
                if task:
                    self._tasks_by_filename.pop(task.filename, None)


# Global conversion manager instance
conversion_manager = ConversionManager()


def is_vrs_file(filename: str) -> bool:
    """Check if file is a VRS file."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'vrs'


def get_vrs_for_video(video_filename: str, folder_path: str) -> Optional[str]:
    """
    Check if a VRS file exists for a given video.
    
    Args:
        video_filename: The video filename (e.g., 'recording.mp4')
        folder_path: Directory to search in
        
    Returns:
        VRS filename if found, None otherwise
    """
    base_name = os.path.splitext(video_filename)[0]
    vrs_filename = f"{base_name}.vrs"
    vrs_path = os.path.join(folder_path, vrs_filename)
    if os.path.exists(vrs_path):
        return vrs_filename
    return None


def get_video_for_vrs(vrs_filename: str, folder_path: str) -> Optional[str]:
    """
    Check if a video file exists for a given VRS file.
    
    Args:
        vrs_filename: The VRS filename (e.g., 'recording.vrs')
        folder_path: Directory to search in
        
    Returns:
        Video filename if found, None otherwise
    """
    base_name = os.path.splitext(vrs_filename)[0]
    video_extensions = ['mp4', 'avi', 'mov', 'mkv', 'webm']
    
    for ext in video_extensions:
        video_filename = f"{base_name}.{ext}"
        video_path = os.path.join(folder_path, video_filename)
        if os.path.exists(video_path):
            return video_filename
    return None


def get_vrs_metadata(vrs_path: str) -> Dict[str, Any]:
    """
    Get metadata from a VRS file using vrs_to_mp4 or vrs CLI.
    
    Args:
        vrs_path: Full path to the VRS file
        
    Returns:
        Dictionary with duration, size, and other metadata
    """
    metadata = {
        'size': 0,
        'duration': None,
        'duration_formatted': None
    }
    
    try:
        # Get file size
        if os.path.exists(vrs_path):
            metadata['size'] = os.path.getsize(vrs_path)
        
        # Try to get VRS metadata using vrs command line tool
        # The vrs tool provides recording information
        try:
            result = subprocess.run(
                ['vrs', 'info', vrs_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                # Parse duration from output
                for line in result.stdout.split('\n'):
                    if 'duration' in line.lower():
                        # Try to extract duration value
                        parts = line.split(':')
                        if len(parts) >= 2:
                            try:
                                duration_str = parts[1].strip()
                                # Duration might be in seconds or HH:MM:SS format
                                if 'seconds' in duration_str.lower():
                                    duration = float(duration_str.split()[0])
                                    metadata['duration'] = duration
                                    metadata['duration_formatted'] = format_duration(duration)
                                    # Found the main duration, stop looking
                                    break
                            except (ValueError, IndexError):
                                pass
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # vrs tool not available, try vrsinfo from projectaria_tools
            pass
            
    except Exception as exc:
        logger.warning("Could not get VRS metadata: %s", exc)
    
    return metadata


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """
    Get metadata from a video file using ffprobe.
    
    Args:
        video_path: Full path to the video file
        
    Returns:
        Dictionary with duration, size, and other metadata
    """
    metadata = {
        'size': 0,
        'duration': None,
        'duration_formatted': None
    }
    
    try:
        # Get file size
        if os.path.exists(video_path):
            metadata['size'] = os.path.getsize(video_path)
        
        # Try to get video duration using ffprobe
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'quiet', '-print_format', 'json',
                    '-show_format', '-show_streams', video_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Try to get duration from format
                if 'format' in data and 'duration' in data['format']:
                    duration = float(data['format']['duration'])
                    metadata['duration'] = duration
                    metadata['duration_formatted'] = format_duration(duration)
                # Fallback to stream duration
                elif 'streams' in data:
                    for stream in data['streams']:
                        if stream.get('codec_type') == 'video' and 'duration' in stream:
                            duration = float(stream['duration'])
                            metadata['duration'] = duration
                            metadata['duration_formatted'] = format_duration(duration)
                            break
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            # ffprobe not available
            pass
            
    except Exception as exc:
        logger.warning("Could not get video metadata: %s", exc)
    
    return metadata


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return "Unknown"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    size = float(size_bytes)
    
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    
    return f"{size:.1f} {units[i]}"


def convert_vrs_to_mp4(
    vrs_path: str,
    output_path: Optional[str] = None,
    rotate: bool = True,
    timeout: int = 600
) -> Tuple[bool, str, Optional[str]]:
    """
    Convert a VRS file to MP4 using projectaria_tools.
    
    Uses the vrs_to_mp4 tool from projectaria_tools to export VRS recordings to MP4.
    
    Note: The rotate parameter is currently ignored as the vrs_to_mp4 CLI does not
    support rotation directly. For rotation support, use the Python API:
    
    from projectaria_tools.utils.calibration_utils import rotate_upright_image_and_calibration
    upright_image, upright_calibration = rotate_upright_image_and_calibration(
        original_rgb_image, rgb_camera_calibration
    )
    
    Reference: https://facebookresearch.github.io/projectaria_tools/docs/data_utilities/advanced_code_snippets/vrs_to_mp4
    
    Args:
        vrs_path: Full path to the input VRS file
        output_path: Full path for output MP4 (optional, defaults to same name with .mp4)
        rotate: Whether to apply rotation correction (currently ignored - not supported by CLI)
        timeout: Timeout in seconds for the conversion process (default: 600)
        
    Returns:
        Tuple of (success: bool, message: str, output_file: Optional[str])
    """
    if not os.path.exists(vrs_path):
        return False, f"VRS file not found: {vrs_path}", None
    
    if output_path is None:
        base_name = os.path.splitext(vrs_path)[0]
        output_path = f"{base_name}.mp4"
    
    # Check if output already exists
    if os.path.exists(output_path):
        return True, f"Output file already exists: {output_path}", output_path
    
    try:
        # Build the vrs_to_mp4 command
        # The tool exports VRS video streams to MP4
        # Note: --output_video is the correct argument (not --output)
        # Note: --rotate-image is not supported, rotation must be done programmatically
        cmd = ['vrs_to_mp4', '--vrs', vrs_path, '--output_video', output_path]
        
        logger.info("Converting VRS to MP4: %s -> %s", vrs_path, output_path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info("VRS conversion successful: %s", output_path)
            return True, "Conversion successful", output_path
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error("VRS conversion failed: %s", error_msg)
            return False, f"Conversion failed: {error_msg}", None
            
    except FileNotFoundError:
        error_msg = (
            "vrs_to_mp4 tool not found. Please install projectaria_tools: "
            "pip install projectaria_tools"
        )
        logger.error(error_msg)
        return False, error_msg, None
    except subprocess.TimeoutExpired:
        error_msg = f"Conversion timed out after {timeout} seconds"
        logger.error(error_msg)
        return False, error_msg, None
    except Exception as exc:
        error_msg = f"Conversion error: {str(exc)}"
        logger.error(error_msg)
        return False, error_msg, None
