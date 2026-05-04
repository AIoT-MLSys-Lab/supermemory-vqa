"""
Routes related to video management and uploads.
"""
import logging
import os
import re
import traceback
import queue
import json as json_module
import time
from functools import lru_cache
from flask import Blueprint, current_app, jsonify, request, send_from_directory, session, Response
from werkzeug.utils import secure_filename

from ..config import get_user_video_folder, set_user_video_folder
from ..extensions import limiter
from ..files import allowed_file, validate_video_content
from ..security import extract_csrf_token, verify_csrf_token
from ..vrs_service import (
    is_vrs_file, get_vrs_for_video, get_video_for_vrs,
    get_vrs_metadata, get_video_metadata, format_size,
    convert_vrs_to_mp4, conversion_manager, ConversionStatus,
    subscribe_to_task_events, unsubscribe_from_task_events
)
from ..thumbnail_service import (
    generate_thumbnail, generate_all_thumbnails,
    get_cached_thumbnail, get_cache_stats, clear_thumbnail_cache,
    CACHE_BUCKET_SIZE
)

logger = logging.getLogger(__name__)
video_bp = Blueprint('videos', __name__)
ANNOTATION_FILE_PATTERN = re.compile(r'^(.+)_annotations_.+\.json$')
V2_ANNOTATION_FILE_PATTERN = re.compile(r'^(.+)_(verified|rejected)_annotations\.json$')

# Cache for annotation index with TTL
_annotation_index_cache = {}
_annotation_index_cache_time = 0
ANNOTATION_INDEX_CACHE_TTL = 5.0  # 5 seconds


def _build_annotation_index() -> dict[str, dict]:
    """Build a lookup dict of video base names to their annotation info.

    Uses in-memory caching with TTL to avoid rebuilding on every request.
    Only counts annotation files, not individual annotations, for better performance.
    """
    global _annotation_index_cache, _annotation_index_cache_time

    # Check if cache is still valid
    current_time = time.time()
    if _annotation_index_cache and (current_time - _annotation_index_cache_time) < ANNOTATION_INDEX_CACHE_TTL:
        return _annotation_index_cache

    import json
    index = {}
    # Get the video folder for current user (may be per-session in multi-user mode)
    upload_folder = get_user_video_folder(current_app.config)
    search_dirs = {upload_folder, current_app.config['ANNOTATIONS_FOLDER']}
    for directory in search_dirs:
        if os.path.exists(directory):
            for candidate in os.listdir(directory):
                legacy_match = ANNOTATION_FILE_PATTERN.match(candidate)
                v2_match = V2_ANNOTATION_FILE_PATTERN.match(candidate)
                if legacy_match:
                    base_name = candidate.split('_annotations_', 1)[0]
                elif v2_match:
                    base_name = v2_match.group(1)
                else:
                    continue
                if base_name not in index:
                    index[base_name] = {'files': 0, 'annotations': 0}
                index[base_name]['files'] += 1
                # Fast count without loading entire file
                try:
                    filepath = os.path.join(directory, candidate)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        annotations = data.get('annotations', [])
                        index[base_name]['annotations'] += len(annotations)
                except (json.JSONDecodeError, OSError, KeyError):
                    pass  # Skip files that can't be read

    # Update cache
    _annotation_index_cache = index
    _annotation_index_cache_time = current_time
    return index


def _video_has_annotations(filename: str, annotation_index: dict[str, dict]) -> bool:
    """Check if a video has any associated annotation files using pre-built index."""
    base_name = os.path.splitext(filename)[0]
    has_annotations = base_name in annotation_index
    # logger.debug(f"Checking annotations for {filename}: {has_annotations}")
    return has_annotations


def _get_annotation_count(filename: str, annotation_index: dict[str, dict]) -> int:
    """Get total annotation count for a video."""
    base_name = os.path.splitext(filename)[0]
    return annotation_index.get(base_name, {}).get('annotations', 0)


def _invalidate_annotation_cache():
    """Invalidate the annotation index cache to force rebuild on next request."""
    global _annotation_index_cache, _annotation_index_cache_time
    _annotation_index_cache = {}
    _annotation_index_cache_time = 0


def _allowed_vrs_file(filename: str, config) -> bool:
    """Check if file is an allowed VRS file."""
    allowed_vrs_extensions = config.get('ALLOWED_VRS_EXTENSIONS', {'vrs'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_vrs_extensions


@video_bp.route('/')
@video_bp.route('/app')
@video_bp.route('/app/<path:path>')
@video_bp.route('/review')
@video_bp.route('/caption-review')
@video_bp.route('/library')
@video_bp.route('/generation')
@limiter.exempt
def serve_svelte_app(path=''):
    """Serve the Svelte frontend application."""
    static_folder = current_app.static_folder
    frontend_folder = os.path.join(static_folder, 'frontend')
    
    if not os.path.exists(frontend_folder):
        logger.error(f"Frontend folder not found at {frontend_folder}")
        # Frontend not built, return error message
        return jsonify({
            'error': 'Frontend not built. Please run: cd frontend && npm install && npm run build'
        }), 503
    
    # Validate path to prevent directory traversal attacks
    if path:
        # Normalize and validate the path
        safe_path = secure_filename(path) if '/' not in path else None
        if safe_path is None:
            # For paths with subdirectories, validate each component
            parts = path.split('/')
            safe_parts = [secure_filename(p) for p in parts if p]
            if not safe_parts or any(p != orig for p, orig in zip(safe_parts, [p for p in parts if p])):
                logger.warning(f"Potential directory traversal attempt: {path}")
                # Path contains unsafe characters, serve index for SPA routing
                return send_from_directory(frontend_folder, 'index.html')
            safe_path = '/'.join(safe_parts)
        
        # Check if file exists within frontend folder
        full_path = os.path.join(frontend_folder, safe_path)
        # Ensure the resolved path is still within frontend_folder
        if os.path.commonpath([os.path.realpath(full_path), os.path.realpath(frontend_folder)]) == os.path.realpath(frontend_folder):
            if os.path.exists(full_path) and os.path.isfile(full_path):
                return send_from_directory(frontend_folder, safe_path)
    
    # Serve index.html for SPA routing
    logger.debug(f"Serving index.html for unknown path: {path}")
    return send_from_directory(frontend_folder, 'index.html')


@video_bp.route('/_app/<path:path>')
@limiter.exempt
def serve_svelte_assets(path):
    """Serve Svelte frontend static assets (_app folder)."""
    static_folder = current_app.static_folder
    frontend_folder = os.path.join(static_folder, 'frontend')
    app_folder = os.path.join(frontend_folder, '_app')
    
    if not os.path.exists(app_folder):
        return jsonify({'error': 'Frontend assets not found'}), 404
    
    # Validate path to prevent directory traversal
    parts = path.split('/')
    safe_parts = [secure_filename(p) for p in parts if p]
    if not safe_parts:
        return jsonify({'error': 'Invalid path'}), 404
    
    safe_path = '/'.join(safe_parts)
    full_path = os.path.join(app_folder, safe_path)
    
    # Ensure the resolved path is still within app_folder
    try:
        if os.path.commonpath([os.path.realpath(full_path), os.path.realpath(app_folder)]) != os.path.realpath(app_folder):
            return jsonify({'error': 'Invalid path'}), 404
    except ValueError:
        return jsonify({'error': 'Invalid path'}), 404
    
    if os.path.exists(full_path) and os.path.isfile(full_path):
        # Determine the directory and filename for send_from_directory
        dir_path = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(dir_path, filename)
    
    return jsonify({'error': 'File not found'}), 404


@video_bp.route('/api/csrf-token')
def get_csrf_token():
    """Return CSRF token for frontend API calls."""
    from ..security import generate_csrf_token
    token = generate_csrf_token()
    return jsonify({'csrf_token': token})


@video_bp.route('/api/session-info')
def get_session_info():
    """Return the current session ID, generating one if needed."""
    if 'session_id' not in session:
        import uuid
        session['session_id'] = str(uuid.uuid4())
    return jsonify({'session_id': session['session_id']})


@video_bp.route('/api/videos')
def list_videos():
    """List all uploaded videos and VRS files with metadata.
    
    Videos are shown with:
    - Green processed status indicator if the file is a video
    - Source VRS file indicator if a .vrs file exists with the same name
    - Duration and size metadata
    
    VRS files are shown:
    - Only if no corresponding MP4 exists (to avoid duplicates)
    - With VRS icon and process button to convert to video
    - Duration and size metadata when available
    """
    items = []
    # Get the video folder for current user (may be per-session in multi-user mode)
    upload_folder = get_user_video_folder(current_app.config)
    annotation_index = _build_annotation_index()
    
    # Track which VRS files have corresponding videos
    vrs_with_videos = set()
    
    # First pass: collect all video files and track VRS associations
    for filename in os.listdir(upload_folder):
        if allowed_file(filename, current_app.config):
            # Check if this video has a source VRS file
            vrs_filename = get_vrs_for_video(filename, upload_folder)
            if vrs_filename:
                vrs_with_videos.add(vrs_filename)
            
            # Get video metadata
            video_path = os.path.join(upload_folder, filename)
            metadata = get_video_metadata(video_path)
            
            items.append({
                'filename': filename,
                'type': 'video',
                'has_annotations': _video_has_annotations(filename, annotation_index),
                'annotations_count': _get_annotation_count(filename, annotation_index),
                'has_source_vrs': vrs_filename is not None,
                'source_vrs_filename': vrs_filename,
                'is_processed': True,  # Videos are always considered processed
                'duration': metadata.get('duration'),
                'duration_formatted': metadata.get('duration_formatted'),
                'size': metadata.get('size', 0),
                'size_formatted': format_size(metadata.get('size', 0))
            })
    
    # Second pass: add VRS files that don't have corresponding videos
    for filename in os.listdir(upload_folder):
        if _allowed_vrs_file(filename, current_app.config):
            # Only show VRS file if there's no corresponding video
            if filename not in vrs_with_videos:
                # Get VRS metadata
                vrs_path = os.path.join(upload_folder, filename)
                metadata = get_vrs_metadata(vrs_path)
                
                items.append({
                    'filename': filename,
                    'type': 'vrs',
                    'has_annotations': _video_has_annotations(filename, annotation_index),
                    'annotations_count': _get_annotation_count(filename, annotation_index),
                    'has_source_vrs': False,
                    'source_vrs_filename': None,
                    'is_processed': False,  # VRS files need processing
                    'duration': metadata.get('duration'),
                    'duration_formatted': metadata.get('duration_formatted'),
                    'size': metadata.get('size', 0),
                    'size_formatted': format_size(metadata.get('size', 0))
                })
    
    return jsonify(items)


@video_bp.route('/api/get-video-folder', methods=['GET'])
def get_video_folder():
    """
    Get the currently configured video folder path.
    
    In multi-user mode (MULTI_USER_MODE=true), returns the folder for the current session.
    In single-user mode (default), returns the globally configured folder.
    """
    try:
        current_folder = get_user_video_folder(current_app.config)
        return jsonify({
            'success': True,
            'data': {
                'folder_path': current_folder
            }
        })
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error getting video folder: %s", exc)
        return jsonify({'error': 'Failed to get video folder'}), 500


@video_bp.route('/api/browse-folders', methods=['POST'])
def browse_folders():
    """
    Browse directories on the server.
    
    Returns a list of subdirectories in the specified path.
    For security, only allows browsing directories that exist and are accessible.
    
    Request body:
        {
            "path": "/absolute/path/to/browse"  # Optional, defaults to current video folder
        }
    
    Returns:
        {
            "success": true,
            "current_path": "/absolute/path",
            "parent_path": "/absolute",  # null if at root
            "directories": [
                {
                    "name": "folder1",
                    "path": "/absolute/path/folder1"
                },
                ...
            ]
        }
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    data = request.get_json() or {}
    requested_path = data.get('path', '').strip()
    
    # If no path provided, use current video folder
    if not requested_path:
        requested_path = get_user_video_folder(current_app.config)
    
    # Validate the path exists and is a directory
    if not os.path.exists(requested_path):
        return jsonify({'error': 'Path does not exist'}), 400
    
    if not os.path.isdir(requested_path):
        return jsonify({'error': 'Path is not a directory'}), 400
    
    try:
        # Resolve to absolute path to prevent relative path issues
        current_path = os.path.abspath(requested_path)
        
        # Get parent directory (None if at root)
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:  # At root
            parent_path = None
        
        # List subdirectories
        directories = []
        try:
            for entry in os.listdir(current_path):
                entry_path = os.path.join(current_path, entry)
                # Only include directories, skip hidden folders and files
                if os.path.isdir(entry_path) and not entry.startswith('.'):
                    directories.append({
                        'name': entry,
                        'path': entry_path
                    })
        except PermissionError:
            logger.warning("Permission denied listing directory: %s", current_path)
            return jsonify({'error': 'Permission denied'}), 403
        
        # Sort directories by name
        directories.sort(key=lambda x: x['name'].lower())
        
        logger.info("Browsed folder: %s (%d subdirectories)", current_path, len(directories))
        return jsonify({
            'success': True,
            'data': {
                'current_path': current_path,
                'parent_path': parent_path,
                'directories': directories
            }
        })
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error browsing folders: %s", exc)
        return jsonify({'error': 'Failed to browse folders'}), 500


@video_bp.route('/api/browse-files', methods=['POST'])
def browse_files():
    """
    Browse directories and video files on the server.
    
    Returns a list of subdirectories and video files in the specified path.
    For security, only allows browsing directories that exist and are accessible.
    
    Request body:
        {
            "path": "/absolute/path/to/browse"  # Optional, defaults to current video folder
        }
    
    Returns:
        {
            "success": true,
            "current_path": "/absolute/path",
            "parent_path": "/absolute",  # null if at root
            "directories": [
                {
                    "name": "folder1",
                    "path": "/absolute/path/folder1"
                },
                ...
            ],
            "video_files": [
                {
                    "name": "video1.mp4",
                    "path": "/absolute/path/video1.mp4"
                },
                ...
            ]
        }
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    data = request.get_json() or {}
    requested_path = data.get('path', '').strip()
    
    # If no path provided, use current video folder
    if not requested_path:
        requested_path = get_user_video_folder(current_app.config)
    
    # Validate the path exists and is a directory
    if not os.path.exists(requested_path):
        return jsonify({'error': 'Path does not exist'}), 400
    
    if not os.path.isdir(requested_path):
        return jsonify({'error': 'Path is not a directory'}), 400
    
    try:
        # Resolve to absolute path to prevent relative path issues
        current_path = os.path.abspath(requested_path)
        
        # Get parent directory (None if at root)
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:  # At root
            parent_path = None
        
        # List subdirectories and video files
        directories = []
        video_files = []
        
        # Video extensions to look for
        video_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'mp4', 'avi', 'mov', 'mkv', 'webm', 'vrs'})
        
        try:
            for entry in os.listdir(current_path):
                entry_path = os.path.join(current_path, entry)
                # Skip hidden files and folders
                if entry.startswith('.'):
                    continue
                    
                if os.path.isdir(entry_path):
                    directories.append({
                        'name': entry,
                        'path': entry_path
                    })
                elif os.path.isfile(entry_path):
                    # Check if it's a video file
                    ext = entry.rsplit('.', 1)[-1].lower() if '.' in entry else ''
                    if ext in video_extensions:
                        video_files.append({
                            'name': entry,
                            'path': entry_path
                        })
        except PermissionError:
            logger.warning("Permission denied listing directory: %s", current_path)
            return jsonify({'error': 'Permission denied'}), 403
        
        # Sort directories and files by name
        directories.sort(key=lambda x: x['name'].lower())
        video_files.sort(key=lambda x: x['name'].lower())
        
        logger.info("Browsed files: %s (%d dirs, %d videos)", current_path, len(directories), len(video_files))
        return jsonify({
            'success': True,
            'data': {
                'current_path': current_path,
                'parent_path': parent_path,
                'directories': directories,
                'video_files': video_files
            }
        })
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error browsing files: %s", exc)
        return jsonify({'error': 'Failed to browse files'}), 500


@video_bp.route('/api/set-video-folder', methods=['POST'])
def set_video_folder():
    """
    Set the video folder path for loading videos.
    
    In multi-user mode (MULTI_USER_MODE=true), this sets the folder per-session.
    In single-user mode (default), this sets the folder globally for all users.
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    data = request.get_json() or {}
    folder_path = data.get('folder_path', '').strip()

    if not folder_path:
        return jsonify({'error': 'No folder path provided'}), 400

    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        logger.error(f"Invalid folder path requested: {folder_path}")
        return jsonify({'error': 'Invalid folder path'}), 400

    try:
        # Use the multi-user aware function to set video folder
        set_user_video_folder(current_app.config, folder_path)

        video_count = sum(1 for file_name in os.listdir(folder_path) if allowed_file(file_name, current_app.config))

        logger.info("Video folder set to: %s (%s videos)", folder_path, video_count)
        return jsonify({
            'success': True,
            'folder_path': folder_path,
            'video_count': video_count
        })
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error setting video folder: %s", exc)
        return jsonify({'error': 'Failed to set video folder'}), 500


@video_bp.route('/api/upload', methods=['POST'])
def upload_video():
    """Upload a video file with content validation."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning(f"CSRF token validation failed during upload. Token: {csrf_token}")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file or not allowed_file(file.filename, current_app.config):
        return jsonify({'error': 'Invalid file type. Allowed: MP4, AVI, MOV, MKV, WebM'}), 400

    try:
        filename = secure_filename(file.filename)
        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        if not validate_video_content(filepath, current_app.config.get('ALLOWED_MIME_TYPES', set())):
            os.remove(filepath)
            logger.warning("Uploaded file failed content validation: %s", filename)
            return jsonify({'error': 'File is not a valid video'}), 400

        logger.info("Video uploaded successfully: %s", filename)
        return jsonify({
            'success': True,
            'filename': filename
        })
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Upload error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Upload failed'}), 500


@video_bp.route('/uploads/<filename>')
@limiter.exempt
def serve_video(filename):
    """Serve uploaded video files."""
    safe_filename = secure_filename(filename)
    if not allowed_file(safe_filename, current_app.config):
        logger.warning("File type not allowed for: %s", filename)
        return jsonify({'error': 'File type not allowed'}), 404

    # Get the video folder for current user (may be per-session in multi-user mode)
    upload_folder = os.path.abspath(get_user_video_folder(current_app.config))
    video_path = os.path.join(upload_folder, safe_filename)

    logger.info("Attempting to serve video: %s from %s", safe_filename, upload_folder)

    if not os.path.exists(video_path):
        logger.error("Video file not found: %s", video_path)
        return jsonify({'error': 'Video file not found'}), 404

    if not os.path.isfile(video_path):
        logger.error("Path exists but is not a file: %s", video_path)
        return jsonify({'error': 'Invalid file path'}), 404

    try:
        logger.info("Serving %s from directory %s", safe_filename, upload_folder)
        return send_from_directory(upload_folder, safe_filename)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error serving video %s - %s", safe_filename, traceback.format_exc())
        return jsonify({'error': 'Failed to serve video'}), 500


@video_bp.route('/api/serve-video')
@limiter.exempt
def serve_external_video():
    """
    Serve a video file from an absolute path.
    
    Query params:
        path: Absolute path to the video file
        
    Security:
        - Validates file exists and is a file
        - Validates file extension against allowed types
    """
    video_path = request.args.get('path', '').strip()
    
    if not video_path:
        return jsonify({'error': 'No path provided'}), 400
        
    # Validation
    if not os.path.isabs(video_path):
        return jsonify({'error': 'Path must be absolute'}), 400
        
    if not os.path.exists(video_path):
        return jsonify({'error': 'File not found'}), 404
        
    if not os.path.isfile(video_path):
        return jsonify({'error': 'Path is not a file'}), 400
        
    # Check extension
    if not allowed_file(os.path.basename(video_path), current_app.config):
        return jsonify({'error': 'File type not allowed'}), 403
        
    try:
        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        logger.info(f"Serving external video: {video_path}")
        return send_from_directory(directory, filename)
    except Exception as exc:
        logger.error(f"Error serving external video {video_path}: {exc}")
        return jsonify({'error': 'Failed to serve video'}), 500


@video_bp.route('/api/videos/thumbnail/<filename>')
@limiter.exempt
def get_thumbnail(filename):
    """
    Get a cached preview thumbnail for a video at a specific timestamp.
    
    Query params:
        t: Timestamp bucket (integer seconds, default 0)
        
    Returns:
        JPEG image if cached, 404 if not cached (client should generate locally)
    """
    safe_filename = secure_filename(filename)
    timestamp_bucket = request.args.get('t', '0', type=int)
    
    # Get video path
    upload_folder = get_user_video_folder(current_app.config)
    video_path = os.path.join(upload_folder, safe_filename)
    
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video not found'}), 404
    
    # Check for cached thumbnail
    thumb_path = get_cached_thumbnail(video_path, timestamp_bucket)
    
    if thumb_path:
        # Serve cached thumbnail
        return send_from_directory(
            thumb_path.parent,
            thumb_path.name,
            mimetype='image/jpeg'
        )
    
    # Generate on-demand
    thumb_path = generate_thumbnail(video_path, timestamp_bucket * CACHE_BUCKET_SIZE)
    
    if thumb_path:
        return send_from_directory(
            thumb_path.parent,
            thumb_path.name,
            mimetype='image/jpeg'
        )
    
    # Generation failed
    return jsonify({'error': 'Failed to generate thumbnail'}), 500


@video_bp.route('/api/videos/thumbnail/<filename>/stats')
@limiter.exempt
def get_thumbnail_stats(filename):
    """Get cache statistics for a video's thumbnails."""
    safe_filename = secure_filename(filename)
    
    upload_folder = get_user_video_folder(current_app.config)
    video_path = os.path.join(upload_folder, safe_filename)
    
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video not found'}), 404
    
    stats = get_cache_stats(video_path)
    return jsonify(stats)


@video_bp.route('/api/videos/thumbnail/<filename>/clear', methods=['POST'])
def clear_thumbnails(filename):
    """Clear the thumbnail cache for a specific video."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        return jsonify({'error': 'Invalid CSRF token'}), 403
    
    safe_filename = secure_filename(filename)
    
    upload_folder = get_user_video_folder(current_app.config)
    video_path = os.path.join(upload_folder, safe_filename)
    
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video not found'}), 404
    
    success = clear_thumbnail_cache(video_path)
    
    return jsonify({
        'success': success,
        'message': 'Cache cleared' if success else 'Failed to clear cache'
    })


@video_bp.route('/api/convert-vrs', methods=['POST'])
def convert_vrs():
    """
    Start a background VRS to MP4 conversion.
    
    Request body:
        {
            "filename": "recording.vrs",
            "rotate": true  // optional, default true
        }
    
    Returns:
        {
            "success": true,
            "task_id": "uuid",
            "filename": "recording.vrs",
            "status": "running",
            "message": "Conversion started"
        }
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403
    
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    rotate = data.get('rotate', True)
    
    if not filename:
        return jsonify({'error': 'No filename provided'}), 400
    
    # Validate filename
    safe_filename = secure_filename(filename)
    if not _allowed_vrs_file(safe_filename, current_app.config):
        return jsonify({'error': 'Invalid file type. Must be a VRS file'}), 400
    
    # Get paths
    upload_folder = get_user_video_folder(current_app.config)
    vrs_path = os.path.join(upload_folder, safe_filename)
    
    if not os.path.exists(vrs_path):
        return jsonify({'error': 'VRS file not found'}), 404
    
    # Generate output path
    base_name = os.path.splitext(safe_filename)[0]
    output_path = os.path.join(upload_folder, f"{base_name}.mp4")
    
    try:
        # Start background conversion
        task = conversion_manager.start_conversion(
            filename=safe_filename,
            vrs_path=vrs_path,
            output_path=output_path,
            rotate=rotate
        )
        logger.info(f"Started VRS conversion task {task.task_id} for {safe_filename}")
        
        return jsonify({
            'success': True,
            'task_id': task.task_id,
            'filename': safe_filename,
            'status': task.status.value,
            'message': 'Conversion started'
        })
            
    except Exception as exc:
        logger.error(f"VRS conversion error for {safe_filename}: {exc}\n{traceback.format_exc()}")
        return jsonify({'error': f'Failed to start conversion: {str(exc)}'}), 500


@video_bp.route('/api/conversion-status/<filename>')
def get_conversion_status(filename):
    """
    Get the status of a VRS conversion for a specific file.
    
    Returns:
        {
            "filename": "recording.vrs",
            "is_processing": true/false,
            "task": { ... task details ... } or null
        }
    """
    safe_filename = secure_filename(filename)
    task = conversion_manager.get_task_by_filename(safe_filename)
    
    return jsonify({
        'filename': safe_filename,
        'is_processing': conversion_manager.is_processing(safe_filename),
        'task': task.to_dict() if task else None
    })


@video_bp.route('/api/conversion-status')
@limiter.exempt
def get_all_conversion_status():
    """
    Get status of all active conversions.
    
    Note: This endpoint is exempt from rate limiting because it's polled
    frequently by the frontend to track conversion progress.
    
    Returns:
        {
            "active_tasks": { task_id: task_details, ... },
            "processing_files": ["file1.vrs", "file2.vrs"]
        }
    """
    active_tasks = conversion_manager.get_active_tasks()
    
    return jsonify({
        'active_tasks': {tid: task.to_dict() for tid, task in active_tasks.items()},
        'processing_files': conversion_manager.get_processing_filenames(),
        'num_workers': conversion_manager.num_workers
    })





@video_bp.route('/api/task-events')
@limiter.exempt
def task_events_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time task status updates.
    
    This replaces polling for task status. The frontend connects once and
    receives push notifications when tasks start, progress, complete, or fail.
    
    Event types:
        - task_started: A new conversion task has started
        - task_progress: Task progress update
        - task_completed: Task completed (success or failure)
        - task_cancelled: Task was cancelled
        - heartbeat: Keep-alive signal (every 30 seconds)
    
    Usage (JavaScript):
        const eventSource = new EventSource('/api/task-events');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Task event:', data);
        };
    """
    logger.info("New SSE connection request received")
    def generate():
        # Create a queue for this client
        client_queue = queue.Queue()
        
        def on_task_event(event_type, task_data):
            """Callback for task events."""
            try:
                # Log completion events at INFO level, others at DEBUG
                if event_type in ('task_completed', 'task_failed'):
                    logger.info(f"Queuing event {event_type} for SSE client: {task_data.get('filename')}")
                else:
                    logger.debug(f"Queuing event {event_type} for SSE client")
                    
                client_queue.put_nowait({
                    'event': event_type,
                    'data': task_data
                })
            except queue.Full:
                logger.warning("SSE client queue full, dropping event")
                pass  # Drop event if queue is full
        
        # Subscribe to task events
        subscribe_to_task_events(on_task_event)
        logger.info("Subscribed SSE client to task events")
        
        try:
            # Send initial state with all active tasks
            active_tasks = conversion_manager.get_active_tasks()
            logger.info(f"Sending initial state with {len(active_tasks)} active tasks")
            initial_data = {
                'event': 'init',
                'data': {
                    'active_tasks': {tid: task.to_dict() for tid, task in active_tasks.items()},
                    'processing_files': conversion_manager.get_processing_filenames(),
                    'num_workers': conversion_manager.num_workers
                }
            }
            yield f"data: {json_module.dumps(initial_data)}\n\n"
            
            # Send events as they come
            heartbeat_counter = 0
            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event = client_queue.get(timeout=30)
                    yield f"data: {json_module.dumps(event)}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    heartbeat_counter += 1
                    # logger.debug(f"Sending heartbeat {heartbeat_counter}")
                    yield f"data: {json_module.dumps({'event': 'heartbeat', 'count': heartbeat_counter})}\n\n"
                    
        except GeneratorExit:
            # Client disconnected
            logger.info("SSE client disconnected")
            pass
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            pass
        finally:
            # Unsubscribe when client disconnects
            unsubscribe_from_task_events(on_task_event)
            logger.info("Unsubscribed SSE client from task events")
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Disable buffering for nginx
        }
    )


@video_bp.route('/api/cancel-conversion', methods=['POST'])
def cancel_conversion():
    """
    Cancel a running VRS conversion.
    
    Request body:
        {
            "filename": "recording.vrs"
        }
        OR
        {
            "task_id": "uuid"
        }
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403
    
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    task_id = data.get('task_id', '').strip()
    
    if not filename and not task_id:
        return jsonify({'error': 'No filename or task_id provided'}), 400
    
    success = False
    if task_id:
        success = conversion_manager.cancel_conversion(task_id)
    elif filename:
        safe_filename = secure_filename(filename)
        success = conversion_manager.cancel_by_filename(safe_filename)
    
    if success:
        return jsonify({
            'success': True,
            'message': 'Conversion cancelled'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Conversion not found or already completed'
        }), 404


@video_bp.route('/api/recreate-video', methods=['POST'])
def recreate_video():
    """
    Recreate a video from its source VRS file (background processing).
    
    This deletes the existing video and re-converts from the VRS source.
    
    Request body:
        {
            "filename": "recording.mp4",
            "rotate": true  // optional, default true
        }
    """
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed")
        return jsonify({'error': 'Invalid CSRF token'}), 403
    
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    rotate = data.get('rotate', True)
    
    if not filename:
        return jsonify({'error': 'No filename provided'}), 400
    
    # Validate filename
    safe_filename = secure_filename(filename)
    if not allowed_file(safe_filename, current_app.config):
        return jsonify({'error': 'Invalid file type'}), 400
    
    # Get paths
    upload_folder = get_user_video_folder(current_app.config)
    video_path = os.path.join(upload_folder, safe_filename)
    
    # Find the source VRS file
    vrs_filename = get_vrs_for_video(safe_filename, upload_folder)
    if not vrs_filename:
        return jsonify({'error': 'No source VRS file found'}), 404
    
    vrs_path = os.path.join(upload_folder, vrs_filename)
    
    try:
        # Delete existing video
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info("Deleted existing video for recreation: %s", video_path)
        
        # Start background conversion using VRS filename as key
        task = conversion_manager.start_conversion(
            filename=vrs_filename,
            vrs_path=vrs_path,
            output_path=video_path,
            rotate=rotate
        )
        
        return jsonify({
            'success': True,
            'task_id': task.task_id,
            'filename': vrs_filename,
            'status': task.status.value,
            'message': 'Recreation started'
        })
            
    except Exception as exc:
        logger.error("Video recreation error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': f'Recreation failed: {str(exc)}'}), 500


@video_bp.route('/api/file-metadata/<filename>')
def get_file_metadata(filename):
    """Get metadata (duration, size) for a video or VRS file."""
    safe_filename = secure_filename(filename)
    upload_folder = get_user_video_folder(current_app.config)
    file_path = os.path.join(upload_folder, safe_filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    if _allowed_vrs_file(safe_filename, current_app.config):
        metadata = get_vrs_metadata(file_path)
    elif allowed_file(safe_filename, current_app.config):
        metadata = get_video_metadata(file_path)
    else:
        return jsonify({'error': 'Invalid file type'}), 400
    
    return jsonify({
        'filename': safe_filename,
        'duration': metadata.get('duration'),
        'duration_formatted': metadata.get('duration_formatted'),
        'size': metadata.get('size', 0),
        'size_formatted': format_size(metadata.get('size', 0))
    })
