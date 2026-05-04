"""
File locking utilities for safe concurrent access to annotation files.

This module provides file locking to prevent race conditions when multiple users
are reading/writing to the same annotation files simultaneously.
"""
import logging
import os
import tempfile
import time
import fcntl
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# Default timeout for acquiring locks (in seconds)
DEFAULT_LOCK_TIMEOUT = 30

# Lock directory for storing lock files - use tempfile for cross-platform compatibility
# Can be overridden via SUPERMEMORY_LOCK_DIR environment variable
LOCK_DIR = os.getenv('SUPERMEMORY_LOCK_DIR', os.path.join(tempfile.gettempdir(), 'supermemory_locks'))


def _ensure_lock_dir():
    """Ensure the lock directory exists."""
    os.makedirs(LOCK_DIR, exist_ok=True)


def _get_lock_path(filepath: str) -> str:
    """Get the lock file path for a given annotation file."""
    _ensure_lock_dir()
    # Create a safe filename based on the absolute path
    safe_name = filepath.replace('/', '_').replace('\\', '_').replace(':', '_')
    return os.path.join(LOCK_DIR, f"{safe_name}.lock")


@contextmanager
def file_lock(filepath: str, timeout: float = DEFAULT_LOCK_TIMEOUT, 
              exclusive: bool = True) -> Generator[None, None, None]:
    """
    Context manager for file locking to prevent concurrent access issues.
    
    Args:
        filepath: Path to the file to lock
        timeout: Maximum time to wait for the lock (seconds)
        exclusive: If True, acquire exclusive (write) lock; if False, acquire shared (read) lock
    
    Yields:
        None - the lock is held for the duration of the context
    
    Raises:
        TimeoutError: If the lock cannot be acquired within the timeout period
        OSError: If there's an error creating or managing the lock file
    
    Example:
        with file_lock('/path/to/annotations.json'):
            # Safe to read/write the file
            with open('/path/to/annotations.json', 'w') as f:
                json.dump(data, f)
    """
    lock_path = _get_lock_path(filepath)
    lock_fd = None
    start_time = time.time()
    
    try:
        # Create or open the lock file
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        
        # Determine lock type
        lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        
        # Try to acquire the lock with timeout
        while True:
            try:
                fcntl.flock(lock_fd, lock_type | fcntl.LOCK_NB)
                logger.debug("Acquired %s lock on %s", 
                           "exclusive" if exclusive else "shared", filepath)
                break
            except (OSError, IOError):
                # Lock is held by another process
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(
                        f"Could not acquire lock on {filepath} within {timeout} seconds. "
                        "Another user may be editing this file."
                    )
                # Wait a bit before retrying
                time.sleep(0.1)
        
        yield
        
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
                logger.debug("Released lock on %s", filepath)
            except (OSError, IOError) as e:
                logger.warning("Error releasing lock on %s: %s", filepath, e)


@contextmanager
def read_lock(filepath: str, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Generator[None, None, None]:
    """
    Context manager for acquiring a shared (read) lock on a file.
    Multiple readers can hold the lock simultaneously, but writers must wait.
    
    Args:
        filepath: Path to the file to lock
        timeout: Maximum time to wait for the lock (seconds)
    
    Yields:
        None - the lock is held for the duration of the context
    """
    with file_lock(filepath, timeout=timeout, exclusive=False):
        yield


@contextmanager
def write_lock(filepath: str, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Generator[None, None, None]:
    """
    Context manager for acquiring an exclusive (write) lock on a file.
    Only one writer can hold the lock, and readers must wait.
    
    Args:
        filepath: Path to the file to lock
        timeout: Maximum time to wait for the lock (seconds)
    
    Yields:
        None - the lock is held for the duration of the context
    """
    with file_lock(filepath, timeout=timeout, exclusive=True):
        yield


def cleanup_stale_locks(max_age_seconds: int = 3600) -> int:
    """
    Clean up stale lock files that are older than max_age_seconds.
    
    Args:
        max_age_seconds: Maximum age of lock files to keep (default: 1 hour)
    
    Returns:
        Number of lock files cleaned up
    """
    if not os.path.exists(LOCK_DIR):
        return 0
    
    cleaned = 0
    current_time = time.time()
    
    for filename in os.listdir(LOCK_DIR):
        if filename.endswith('.lock'):
            lock_path = os.path.join(LOCK_DIR, filename)
            try:
                file_age = current_time - os.path.getmtime(lock_path)
                if file_age > max_age_seconds:
                    os.remove(lock_path)
                    cleaned += 1
                    logger.debug("Cleaned up stale lock file: %s", lock_path)
            except OSError as e:
                logger.warning("Error cleaning up lock file %s: %s", lock_path, e)
    
    if cleaned > 0:
        logger.info("Cleaned up %d stale lock files", cleaned)
    
    return cleaned
