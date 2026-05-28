"""
Application configuration and persistence helpers.

This module supports both single-user and multi-user configurations:
- Single-user mode (default): Video folder is stored globally in .video_folder_config
- Multi-user mode (MULTI_USER_MODE=true): Each user session has its own video folder setting

For multi-user deployments, set MULTI_USER_MODE=true in the .env file.
"""
import logging
import os
import secrets

from dotenv import load_dotenv
from flask import session

from .extensions import limiter

# Load environment variables on module import
load_dotenv()

logger = logging.getLogger(__name__)

VIDEO_FOLDER_CONFIG_FILE = '.video_folder_config'
SESSION_VIDEO_FOLDER_KEY = 'user_video_folder'


def is_multi_user_mode() -> bool:
    """Check if multi-user mode is enabled via environment variable."""
    return os.getenv('MULTI_USER_MODE', 'false').lower() == 'true'


def load_video_folder_config(default_folder: str = 'uploads') -> str:
    """Load persisted video folder configuration (global fallback)."""
    if os.path.exists(VIDEO_FOLDER_CONFIG_FILE):
        try:
            with open(VIDEO_FOLDER_CONFIG_FILE, 'r', encoding='utf-8') as config_file:
                folder_path = config_file.read().strip()
                if folder_path and os.path.exists(folder_path) and os.path.isdir(folder_path):
                    logger.info("Loaded video folder from config: %s", folder_path)
                    return folder_path
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error loading video folder config: %s", exc)
    return default_folder


def save_video_folder_config(folder_path: str) -> None:
    """Persist the selected video folder to disk (global setting)."""
    try:
        with open(VIDEO_FOLDER_CONFIG_FILE, 'w', encoding='utf-8') as config_file:
            config_file.write(folder_path)
        logger.info("Saved video folder to config: %s", folder_path)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error saving video folder config: %s", exc)


def get_user_video_folder(app_config: dict, default_folder: str = 'uploads') -> str:
    """
    Get the video folder for the current user/session.
    
    In multi-user mode, each session has its own video folder setting stored in the session.
    In single-user mode, returns the global setting from app config.
    
    Args:
        app_config: Flask app.config dictionary
        default_folder: Default folder if none is configured
        
    Returns:
        Path to the video folder for the current user
    """
    if is_multi_user_mode():
        # Multi-user mode: check session first
        session_folder = session.get(SESSION_VIDEO_FOLDER_KEY)
        if session_folder and os.path.exists(session_folder) and os.path.isdir(session_folder):
            # Validate to prevent path traversal - ensure it's a real path
            real_path = os.path.realpath(session_folder)
            if os.path.exists(real_path) and os.path.isdir(real_path):
                return real_path
        # Fall back to app default if session doesn't have a folder set
        return app_config.get('UPLOAD_FOLDER', default_folder)
    else:
        # Single-user mode: use global config
        return app_config.get('UPLOAD_FOLDER', default_folder)


def set_user_video_folder(app_config: dict, folder_path: str) -> None:
    """
    Set the video folder for the current user/session.
    
    In multi-user mode, stores the setting in the session (per-user).
    In single-user mode, updates the global app config and persists to disk.
    
    Args:
        app_config: Flask app.config dictionary
        folder_path: Path to set as the video folder
    """
    if is_multi_user_mode():
        # Multi-user mode: store in session only (per-user setting)
        session[SESSION_VIDEO_FOLDER_KEY] = folder_path
        logger.info("Set session video folder to: %s", folder_path)
    else:
        # Single-user mode: update global config and persist
        app_config['UPLOAD_FOLDER'] = folder_path
        save_video_folder_config(folder_path)


def apply_default_config(app):
    """Apply base configuration and ensure required folders exist."""
    app.config['SECRET_KEY'] = os.getenv(
        'SECRET_KEY',
        app.config.get('SECRET_KEY') or secrets.token_hex(32)
    )
    app.config.setdefault(
        'SESSION_COOKIE_SECURE',
        os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    )
    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')

    # Load default upload folder: prioritize DEFAULT_VIDEO_FOLDER from environment if set,
    # otherwise load from .video_folder_config, falling back to 'uploads'
    env_default = os.getenv('DEFAULT_VIDEO_FOLDER')
    if env_default:
        env_default = env_default.strip().strip('"').strip("'")
        app.config.setdefault('UPLOAD_FOLDER', env_default)
    else:
        app.config.setdefault('UPLOAD_FOLDER', load_video_folder_config('uploads'))
    app.config.setdefault('ANNOTATIONS_FOLDER', 'annotations')
    workspace_roots = os.getenv('VIDEO_WORKSPACE_ROOTS', '').strip()
    app.config.setdefault(
        'VIDEO_WORKSPACE_ROOTS',
        [root.strip() for root in workspace_roots.split(os.pathsep) if root.strip()]
    )
    app.config.setdefault('MAX_CONTENT_LENGTH', 500 * 1024 * 1024)  # 500MB
    app.config.setdefault('ALLOWED_EXTENSIONS', {'mp4', 'avi', 'mov', 'mkv', 'webm'})
    app.config.setdefault('ALLOWED_VRS_EXTENSIONS', {'vrs'})
    app.config.setdefault(
        'ALLOWED_MIME_TYPES',
        {'video/mp4', 'video/x-msvideo', 'video/quicktime', 'video/x-matroska', 'video/webm'}
    )
    
    # Semantic search configuration
    app.config.setdefault(
        'SEMANTIC_SEARCH_LIMIT',
        int(os.getenv('SEMANTIC_SEARCH_LIMIT', '5'))
    )
    app.config.setdefault(
        'SEMANTIC_SEARCH_THRESHOLD',
        float(os.getenv('SEMANTIC_SEARCH_THRESHOLD', '0.65'))
    )
    
    # Multi-user mode configuration
    app.config.setdefault('MULTI_USER_MODE', is_multi_user_mode())
    
    # Log multi-user mode status
    if app.config['MULTI_USER_MODE']:
        logger.info("Multi-user mode ENABLED - video folder settings are per-session")
    else:
        logger.info("Single-user mode - video folder setting is global")

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ANNOTATIONS_FOLDER'], exist_ok=True)

    limiter.init_app(app)

    return app
