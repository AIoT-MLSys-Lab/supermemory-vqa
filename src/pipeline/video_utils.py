"""
Video Utilities for Pipeline v2
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional

import ffmpeg

# Try to import decord for faster video reading
try:
    import decord
    from decord import VideoReader, cpu
    DECORD_AVAILABLE = True
    # Configure decord to use CPU
    decord.bridge.set_bridge('native')
except ImportError:
    DECORD_AVAILABLE = False
    VideoReader = None

logger = logging.getLogger(__name__)


def extract_session_number(video_path: str) -> int:
    """
    Extract the session number from filenames like 'samiul_10_...'.
    Returns a large number if parsing fails to put it at the end of sorting.
    """
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    parts = base_name.lower().split('_')
    if len(parts) >= 2 and parts[0] == 'samiul':
        try:
            return int(parts[1])
        except ValueError:
            pass
    return 999999  # Fallback for non-standard names


def get_video_duration(video_path: str) -> float:
    """Get the duration of a video file in seconds.

    Uses decord for faster video metadata reading when available,
    falls back to ffprobe otherwise.
    """
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    # Robust VRS discovery: map samiul_N to session_N
    parts = base_name.lower().split('_')
    if len(parts) >= 3 and parts[0] == 'samiul':
        session_num = parts[1]
        date_str = parts[2]
        pattern_name = f"session_{session_num}_{date_str}*.vrs.json"
    else:
        pattern_name = f"{base_name}*.vrs.json"
        
    import glob
    from .config import PIPELINE_V2_CONFIG
    search_dirs = [
        os.path.dirname(video_path),
        PIPELINE_V2_CONFIG.get("DEFAULT_VIDEO_FOLDER", "/local/scratch_2/supermemory_dataset/samiul/loc_0")
    ]
    
    vrs_json_path = None
    for d in search_dirs:
        pattern = os.path.join(d, pattern_name)
        matches = glob.glob(pattern)
        if matches:
            vrs_json_path = matches[0]
            break

    # Try looking for vrs sidecar
    if vrs_json_path and os.path.exists(vrs_json_path):
        try:
            with open(vrs_json_path, 'r') as f:
                data = json.load(f)
                if 'start_time' in data and 'end_time' in data:
                    dur = float(data['end_time'] - data['start_time'])
                    if dur > 0:
                        return dur
        except Exception as e:
            logger.warning(f"Failed to read duration from {vrs_json_path}: {e}")

    # Try decord first if available (faster)
    if DECORD_AVAILABLE:
        try:
            vr = VideoReader(video_path, ctx=cpu(0))
            fps = vr.get_avg_fps()
            num_frames = len(vr)
            duration = num_frames / fps
            logger.debug(f"Got duration {duration:.2f}s from decord for {video_path}")
            return duration
        except Exception as e:
            logger.debug(f"Decord failed to read {video_path}, falling back to ffprobe: {e}")

    # Fallback to ffprobe
    try:
        probe = ffmpeg.probe(video_path)
        return float(probe['format']['duration'])
    except Exception as e:
        logger.error(f"Failed to probe video duration for {video_path}: {e}")
        return 0.0


def get_video_start_time(video_path: str) -> float:
    """Get the start time of the video from its vrs.json sidecar.
    Fails if the sidecar cannot be found to prevent timeline corruption."""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    parts = base_name.lower().split('_')
    if len(parts) >= 3 and parts[0] == 'samiul':
        session_num = parts[1]
        date_str = parts[2]
        pattern_name = f"session_{session_num}_{date_str}*.vrs.json"
    else:
        pattern_name = f"{base_name}*.vrs.json"
        
    import glob
    from .config import PIPELINE_V2_CONFIG
    search_dirs = [
        os.path.dirname(video_path),
        PIPELINE_V2_CONFIG.get("DEFAULT_VIDEO_FOLDER", "/local/scratch_2/supermemory_dataset/samiul/loc_0")
    ]
    
    vrs_json_path = None
    for d in search_dirs:
        pattern = os.path.join(d, pattern_name)
        matches = glob.glob(pattern)
        if matches:
            vrs_json_path = matches[0]
            break
            
    if not vrs_json_path or not os.path.exists(vrs_json_path):
        raise FileNotFoundError(f"CRITICAL: Could not find VRS sidecar for {base_name} in {search_dirs}. "
                                "A .vrs.json file is REQUIRED to establish the global timeline.")

    try:
        with open(vrs_json_path, 'r') as f:
            data = json.load(f)
            if 'start_time' in data:
                return float(data['start_time'])
            else:
                raise ValueError(f"No start_time found in {vrs_json_path}")
    except Exception as e:
        logger.warning(f"Failed to read start time from {vrs_json_path}: {e}")
        raise e


def timestamp_to_seconds(timestamp: str) -> float:
    """Convert MM:SS or HH:MM:SS timestamp to seconds.
    Hardened to handle potential LLM formatting artifacts like spaces.
    """
    clean_ts = str(timestamp).replace(" ", "")
    parts = clean_ts.split(':')
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        else:
            return float(clean_ts)
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {timestamp}")


def offset_time_string(time_str: str, offset_seconds: float) -> str:
    """Offset a MM:SS or HH:MM:SS string by a given number of seconds."""
    try:
        clean_time = str(time_str).replace(" ", "")
        parts = clean_time.split(':')
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            hours = 0
        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        else:
            # Try to parse as float if no colons
            return f"{max(0, float(clean_time) + offset_seconds):.2f}"
            
        total_seconds = hours * 3600 + minutes * 60 + seconds + int(offset_seconds)
        total_seconds = max(0, total_seconds)
        
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except Exception as e:
        logger.warning(f"Failed to offset time string {time_str}: {e}")
        return time_str


def split_video_into_chunks(
        video_path: str,
        video_id: str,
        chunk_duration: int,
        overlap_duration: int,
        min_chunk_duration: int,
        max_chunks_per_video: int,
        chunk_fps: int = 4,
        output_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Split a long video into overlapping chunks for inference."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='video_chunks_')

    os.makedirs(output_dir, exist_ok=True)
    total_duration = get_video_duration(video_path)
    logger.info(f"Video duration: {total_duration:.2f} seconds")

    chunks = []
    chunk_index = 0
    start_time = 0
    reused_count = 0

    while start_time < total_duration:
        if max_chunks_per_video > 0 and chunk_index >= max_chunks_per_video:
            break

        if start_time + chunk_duration >= total_duration:
            end_time = total_duration
        else:
            next_start = (start_time + chunk_duration - overlap_duration)
            remaining_after_next = total_duration - next_start
            if 0 < remaining_after_next < min_chunk_duration:
                end_time = total_duration
            else:
                end_time = start_time + chunk_duration

        chunk_filename = f"{video_id}_{int(start_time)}_{int(end_time)}.mp4"
        chunk_path = os.path.join(output_dir, chunk_filename)

        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            reused_count += 1
        else:
            try:
                (
                    ffmpeg
                    .input(video_path, ss=start_time, t=end_time - start_time)
                    .output(
                        chunk_path,
                        vcodec='libx264',
                        acodec='aac',
                        r=chunk_fps,
                        format='mp4',
                        **{'avoid_negative_ts': 'make_zero'}
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, quiet=True)
                )
            except ffmpeg.Error as e:
                logger.error(f"Error creating chunk {chunk_index}: {e.stderr.decode()}")
                raise

        chunks.append({
            'video_id': video_id,
            'path': chunk_path,
            'start_time': start_time,
            'end_time': end_time,
            'chunk_index': chunk_index
        })

        chunk_index += 1
        if end_time >= total_duration:
            break

        if max_chunks_per_video > 0 and chunk_index >= max_chunks_per_video:
            break

        next_start = end_time - overlap_duration
        if next_start <= start_time:
            break
        start_time = next_start

    logger.info(f"Prepared {len(chunks)} chunks in {output_dir} ({reused_count} reused)")
    return chunks

def extract_and_concatenate_audio(video_metas: List[Dict[str, Any]], output_path: str) -> str:
    """Extract audio from multiple videos and concatenate into a single file."""
    import subprocess
    
    # Create a concat demuxer file
    concat_file_path = output_path + ".txt"
    with open(concat_file_path, 'w') as f:
        for meta in video_metas:
            # ffmpeg concat demuxer expects single quotes around file paths
            # and proper escaping if needed. simpler to just use absolute paths
            f.write(f"file '{meta['path']}'\n")
            
    # Run ffmpeg
    try:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", concat_file_path, 
            "-c:a", "libmp3lame", "-q:a", "2", 
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Concatenated audio written to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to concatenate audio: {e}")
        return ""
    finally:
        if os.path.exists(concat_file_path):
            os.remove(concat_file_path)

def run_whisperx(audio_path: str, model_name: str, device: str, hf_token: str) -> Dict[str, Any]:
    """Run WhisperX with diarization."""
    try:
        import whisperx
        import torch
        import gc
        from whisperx.diarize import DiarizationPipeline
    except ImportError:
        logger.error("whisperx is not installed. Please install it to use this feature.")
        return {}
        
    device_to_use = device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA requested but not available. Falling back to CPU for WhisperX.")
        device_to_use = "cpu"
        
    compute_type = "float16" if device_to_use == "cuda" else "int8"
    
    logger.info(f"Loading WhisperX model '{model_name}' on {device_to_use}...")
    try:
        model = whisperx.load_model(model_name, device_to_use, compute_type=compute_type)
        
        logger.info("Transcribing audio...")
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=8)
        
        # Cleanup model to save VRAM
        if device_to_use == "cuda":
            del model
            gc.collect()
            torch.cuda.empty_cache()

        logger.info("Aligning transcript...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device_to_use)
        result = whisperx.align(result["segments"], model_a, metadata, audio, device_to_use, return_char_alignments=False)
        
        # Cleanup align model
        if device_to_use == "cuda":
            del model_a
            gc.collect()
            torch.cuda.empty_cache()

        if hf_token:
            logger.info("Diarizing speakers...")
            # Use 'token' as shown in the user's working example
            diarize_model = DiarizationPipeline(token=hf_token, device=device_to_use)
            diarize_segments = diarize_model(audio, min_speakers=1, max_speakers=10)
            result = whisperx.assign_word_speakers(diarize_segments, result)
        else:
            logger.warning("HF_TOKEN not found. Skipping diarization.")
            
        return result
    except Exception as e:
        logger.error(f"WhisperX transcription failed: {e}")
        return {}

def split_transcript_by_video(global_transcript: Dict[str, Any], video_metas: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Split the global diarized transcript back into per-video transcripts based on duration."""
    per_video_transcripts = {meta['video_id']: [] for meta in video_metas}
    
    if not global_transcript or "segments" not in global_transcript:
        return per_video_transcripts
        
    # Calculate global start and end times for each video based on concatenation
    current_time = 0.0
    video_timings = []
    for meta in video_metas:
        duration = meta.get('duration', 0.0)
        video_timings.append({
            'video_id': meta['video_id'],
            'global_start': current_time,
            'global_end': current_time + duration
        })
        current_time += duration
        
    # Assign segments to videos
    for segment in global_transcript["segments"]:
        seg_start = segment.get("start", 0.0)
        seg_end = segment.get("end", 0.0)
        
        # Find which video this segment primarily belongs to
        best_match_id = None
        best_overlap = 0.0
        
        for timing in video_timings:
            # Calculate overlap
            overlap_start = max(seg_start, timing['global_start'])
            overlap_end = min(seg_end, timing['global_end'])
            overlap = max(0.0, overlap_end - overlap_start)
            
            if overlap > best_overlap:
                best_overlap = overlap
                best_match_id = timing['video_id']
                
        if best_match_id:
            # Adjust timestamps to be relative to the video
            video_timing = next(t for t in video_timings if t['video_id'] == best_match_id)
            rel_start = max(0.0, seg_start - video_timing['global_start'])
            rel_end = max(0.0, seg_end - video_timing['global_start'])
            
            per_video_transcripts[best_match_id].append({
                "start": rel_start,
                "end": rel_end,
                "text": segment.get("text", "").strip(),
                "speaker": segment.get("speaker", "UNKNOWN")
            })
            
    return per_video_transcripts

def validate_video_clip(video_path: str) -> bool:
    """
    Validates that a video clip is healthy and playable using ffprobe.
    Checks for:
    1. File existence and non-zero size.
    2. Successful ffprobe parse.
    3. Presence of at least one video stream.
    4. Non-zero duration.
    """
    if not os.path.exists(video_path):
        logger.error(f"Validation failed: File does not exist: {video_path}")
        return False
        
    if os.path.getsize(video_path) == 0:
        logger.error(f"Validation failed: File is empty: {video_path}")
        return False
        
    try:
        # Probe the file
        probe = ffmpeg.probe(video_path)
        
        # Check for video streams
        video_streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'video']
        if not video_streams:
            logger.error(f"Validation failed: No video stream found in {video_path}")
            return False
            
        # Check duration
        duration = float(probe.get('format', {}).get('duration', 0))
        if duration <= 0:
            logger.error(f"Validation failed: Duration is zero for {video_path}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Validation failed: ffprobe error for {video_path}: {e}")
        return False
