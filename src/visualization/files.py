"""
Reusable file utilities for the visualization layer.
"""
import logging
import os
from typing import Optional, Mapping, Any

import magic
from flask import current_app
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

DEFAULT_FILE_CONFIG = {
    'ALLOWED_EXTENSIONS': set(),
    'ALLOWED_MIME_TYPES': set(),
    'ANNOTATIONS_FOLDER': 'annotations'
}


def _get_config(config: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    if config is not None:
        return config
    try:
        return current_app.config
    except RuntimeError as exc:  # pragma: no cover - explicit failure when no app context
        logger.error("File helpers require a Flask application context or explicit config: %s", exc)
        raise RuntimeError("Flask application context or explicit config is required") from exc


def allowed_file(filename: str, config: Optional[Mapping[str, Any]] = None) -> bool:
    """Check if file extension is allowed."""
    cfg = _get_config(config)
    allowed_extensions = cfg.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def validate_video_content(
    filepath: str,
    allowed_mime_types: Optional[set] = None
) -> bool:
    """
    Validate that uploaded file is actually a video by checking magic bytes.
    """
    mime_types = allowed_mime_types
    if mime_types is None:
        cfg = _get_config()
        mime_types = cfg.get('ALLOWED_MIME_TYPES', set())

    try:
        mime = magic.Magic(mime=True)
        file_mime = mime.from_file(filepath)
        is_valid = file_mime in mime_types
        if not is_valid:
            logger.warning("Invalid video file type: %s", file_mime)
        return is_valid
    except Exception as exc:
        logger.error("Error validating file content: %s", exc)
        return False


def get_annotation_path(
    video_filename: str,
    config: Optional[Mapping[str, Any]] = None
) -> str:
    """
    Get the path to the annotation file for a video with filename sanitization.
    """
    cfg = _get_config(config)
    annotations_folder = cfg.get('ANNOTATIONS_FOLDER', 'annotations')

    safe_filename = secure_filename(os.path.basename(video_filename))
    if not safe_filename or safe_filename.strip() == '':
        raise ValueError("Invalid or empty filename")

    base_name = os.path.splitext(safe_filename)[0]
    return os.path.join(annotations_folder, f"{base_name}_annotations.json")
