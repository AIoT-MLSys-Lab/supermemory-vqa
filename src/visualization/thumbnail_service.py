"""
Thumbnail caching service for video preview frames.

Generates and caches low-resolution preview thumbnails from videos using FFmpeg.
Thumbnails are stored on disk for persistence across page reloads.
"""
import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Constants
THUMBNAIL_WIDTH = 160  # pixels
THUMBNAIL_QUALITY = 5  # FFmpeg quality (2-31, lower is better)
CACHE_BUCKET_SIZE = 1  # seconds per thumbnail
CACHE_DIR_NAME = ".cache"
PREVIEWS_DIR_NAME = "previews"


def get_video_hash(video_path: str) -> str:
    """Generate a short hash for the video filename to use as cache directory name."""
    # Use filename + file size for uniqueness (faster than hashing file content)
    filename = os.path.basename(video_path)
    try:
        file_size = os.path.getsize(video_path)
        identifier = f"{filename}_{file_size}"
    except OSError:
        identifier = filename
    
    return hashlib.md5(identifier.encode()).hexdigest()[:12]


def get_cache_dir(video_path: str) -> Path:
    """
    Get the cache directory path for a video's thumbnails.
    
    Creates the directory structure if it doesn't exist:
    {video_folder}/.cache/previews/{video_hash}/
    """
    video_dir = os.path.dirname(os.path.abspath(video_path))
    video_hash = get_video_hash(video_path)
    
    cache_dir = Path(video_dir) / CACHE_DIR_NAME / PREVIEWS_DIR_NAME / video_hash
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    return cache_dir


def get_thumbnail_filename(timestamp_bucket: int) -> str:
    """Get the filename for a thumbnail at a given timestamp bucket."""
    return f"thumb_{timestamp_bucket:05d}.jpg"


def get_thumbnail_path(video_path: str, timestamp_bucket: int) -> Path:
    """Get the full path to a cached thumbnail."""
    cache_dir = get_cache_dir(video_path)
    return cache_dir / get_thumbnail_filename(timestamp_bucket)


def thumbnail_exists(video_path: str, timestamp_bucket: int) -> bool:
    """Check if a cached thumbnail exists for the given timestamp bucket."""
    thumb_path = get_thumbnail_path(video_path, timestamp_bucket)
    return thumb_path.exists() and thumb_path.stat().st_size > 0


def get_cached_thumbnail(video_path: str, timestamp_bucket: int) -> Optional[Path]:
    """
    Get the path to a cached thumbnail if it exists.
    
    Returns None if thumbnail doesn't exist.
    """
    thumb_path = get_thumbnail_path(video_path, timestamp_bucket)
    if thumb_path.exists() and thumb_path.stat().st_size > 0:
        return thumb_path
    return None


def generate_thumbnail(video_path: str, timestamp_seconds: float) -> Optional[Path]:
    """
    Generate a thumbnail for the video at the specified timestamp.
    
    Uses FFmpeg to extract a single frame and save as JPEG.
    Returns the path to the generated thumbnail, or None on failure.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        return None
    
    bucket = int(timestamp_seconds // CACHE_BUCKET_SIZE)
    thumb_path = get_thumbnail_path(video_path, bucket)
    
    # If already exists, return it
    if thumb_path.exists() and thumb_path.stat().st_size > 0:
        return thumb_path
    
    # Generate using FFmpeg
    # -ss before -i for fast seeking
    # -vframes 1 to extract single frame
    # -vf scale to resize
    # -q:v for quality
    cmd = [
        "ffmpeg",
        "-ss", str(timestamp_seconds),
        "-i", video_path,
        "-vframes", "1",
        "-vf", f"scale={THUMBNAIL_WIDTH}:-1",
        "-q:v", str(THUMBNAIL_QUALITY),
        "-y",  # Overwrite if exists
        str(thumb_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,  # 10 second timeout per thumbnail
        )
        
        if result.returncode != 0:
            logger.warning(f"FFmpeg failed for {video_path} at {timestamp_seconds}s: {result.stderr.decode()[:200]}")
            return None
        
        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            logger.debug(f"Generated thumbnail: {thumb_path}")
            return thumb_path
        else:
            logger.warning(f"Thumbnail file not created: {thumb_path}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg timeout generating thumbnail for {video_path} at {timestamp_seconds}s")
        return None
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        return None


def get_video_duration(video_path: str) -> Optional[float]:
    """Get the duration of a video in seconds using FFprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode == 0:
            return float(result.stdout.decode().strip())
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
    
    return None


def generate_all_thumbnails(video_path: str, interval: float = 1.0) -> list[Path]:
    """
    Pre-generate all thumbnails for a video at the specified interval.
    
    Returns a list of paths to generated thumbnails.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        return []
    
    duration = get_video_duration(video_path)
    if not duration:
        logger.error(f"Could not get duration for {video_path}")
        return []
    
    generated = []
    timestamp = 0.0
    
    while timestamp < duration:
        thumb_path = generate_thumbnail(video_path, timestamp)
        if thumb_path:
            generated.append(thumb_path)
        timestamp += interval
    
    logger.info(f"Generated {len(generated)} thumbnails for {os.path.basename(video_path)}")
    return generated


def clear_thumbnail_cache(video_path: str) -> bool:
    """
    Clear the thumbnail cache for a specific video.
    
    Returns True if cache was cleared successfully.
    """
    try:
        cache_dir = get_cache_dir(video_path)
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir)
            logger.info(f"Cleared thumbnail cache: {cache_dir}")
            return True
    except Exception as e:
        logger.error(f"Error clearing thumbnail cache: {e}")
    
    return False


def get_cache_stats(video_path: str) -> dict:
    """Get statistics about the thumbnail cache for a video."""
    cache_dir = get_cache_dir(video_path)
    
    if not cache_dir.exists():
        return {"exists": False, "count": 0, "size_bytes": 0}
    
    thumbnails = list(cache_dir.glob("thumb_*.jpg"))
    total_size = sum(t.stat().st_size for t in thumbnails)
    
    return {
        "exists": True,
        "count": len(thumbnails),
        "size_bytes": total_size,
        "cache_dir": str(cache_dir),
    }
