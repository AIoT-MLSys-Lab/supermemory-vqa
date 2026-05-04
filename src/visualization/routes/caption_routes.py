"""
Routes for caption file CRUD operations.

Caption files are JSON files stored alongside videos with the naming convention:
    {video_base}_captions_{caption_type}.json

Each caption file contains:
    {
        "caption_type": "narration",
        "captions": [
            {"text": "...", "start": "0:15", "end": "0:45"},
            ...
        ],
        "human_review": {"status": "pending", ...},
        "metadata": {...}
    }
"""
import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from ..caption_search import parse_search_request_args, search_captions
from ..config import get_user_video_folder
from ..extensions import limiter
from ..security import extract_csrf_token, verify_csrf_token

logger = logging.getLogger(__name__)
caption_bp = Blueprint('captions', __name__)


def _safe_video_dir(video_filename: str):
    """Return (safe_filename, video_dir) or raise ValueError."""
    safe_filename = secure_filename(os.path.basename(video_filename))
    if not safe_filename:
        raise ValueError('Invalid filename')
    upload_folder = get_user_video_folder(current_app.config)
    video_path = os.path.join(upload_folder, safe_filename)
    return safe_filename, os.path.dirname(video_path)


def _find_caption_file(video_dir: str, caption_filename: str) -> str:
    """Locate a caption file in the video directory."""
    candidate = os.path.join(video_dir, caption_filename)
    if os.path.exists(candidate):
        real_dir = Path(video_dir).resolve()
        real_candidate = Path(candidate).resolve()
        if real_candidate.is_relative_to(real_dir):
            return candidate
    return ''


def _load_caption_file(path: str) -> dict:
    """Load and return parsed caption JSON.

    Handles both the legacy flat format and the new pipeline_v2
    chunk-based ``*_caption_narrations.json`` format.  The new format is
    normalised into the flat structure expected by the frontend:

    * ``caption_type`` – derived from the filename
    * ``captions`` – list of ``{text, start, end, importance, confidence, description}``
    * ``chunks`` – the original chunk data is preserved for round-tripping
    * ``chunk_summaries`` – list of ``overall_summary`` strings per chunk
    * ``metadata`` – ``{video_id, video_path, duration, start_time}``
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Detect new pipeline_v2 chunk-based format.  Re-normalise whenever
    # 'chunks' exists so that reasoning fields added to _normalise_caption_narrations
    # are always picked up – even for files that were previously saved with
    # both 'chunks' and 'captions' but before the reasoning fields were propagated.
    if 'chunks' in data:
        data = _normalise_caption_narrations(data, path)

    return data


def _normalise_caption_narrations(data: dict, path: str) -> dict:
    """Convert new chunk-based caption narration format to flat frontend format."""

    captions = []
    chunk_summaries = []
    for chunk in data.get('chunks', []):
        caption_block = chunk.get('caption', {})
        summary = caption_block.get('overall_summary', '')
        if summary:
            chunk_summaries.append(summary)

        for seg in caption_block.get('segments', []):
            ts = seg.get('time_span', {})
            desc_raw = seg.get('description', {})

            # objects may be a list of strings or other values – join for display
            objects_val = desc_raw.get('objects', '')
            if isinstance(objects_val, list):
                objects_val = ', '.join(str(o) for o in objects_val)

            # audio_transcript: preserve as structured list if available
            audio_val = desc_raw.get('audio_transcript', '')
            if isinstance(audio_val, list):
                # Keep as list of {speaker, transcript} dicts
                audio_val = [
                    {'speaker': item.get('speaker', None), 'transcript': item.get('transcript', str(item))}
                    if isinstance(item, dict) else {'speaker': None, 'transcript': str(item)}
                    for item in audio_val
                ]
            elif audio_val is None:
                audio_val = []

            # visible_text may be None in the new schema
            visible_text = desc_raw.get('visible_text', '')
            if visible_text is None:
                visible_text = ''

            # people: preserve as structured list if available
            people_val = desc_raw.get('people', '')
            if isinstance(people_val, list):
                # Keep as list of {person, description} dicts
                people_val = [
                    {'person': item.get('person', ''), 'description': item.get('description', str(item))}
                    if isinstance(item, dict) else {'person': '', 'description': str(item)}
                    for item in people_val
                ]
            elif people_val is None:
                people_val = []

            description = {
                'activities': desc_raw.get('activities', '') or '',
                'environment': desc_raw.get('environment', '') or '',
                'visible_text': visible_text,
                'objects': objects_val,
                'audio_transcript': audio_val,
                'people': people_val,
            }

            # Build a combined text fallback
            text_parts = [p for p in [
                description['activities'],
                f"Objects: {description['objects']}" if description['objects'] else '',
                f"Environment: {description['environment']}" if description['environment'] else '',
            ] if p]

            captions.append({
                'text': '. '.join(text_parts),
                'start': ts.get('start_time', '0:00'),
                'end': ts.get('end_time', '0:00'),
                'importance': seg.get('importance', 'medium'),
                'importance_reasoning': seg.get('importance_reasoning', ''),
                'confidence': seg.get('confidence', 'medium'),
                'confidence_reasoning': seg.get('confidence_reasoning', ''),
                'description': description,
                'optimal_sampling_rate': seg.get('optimal_sampling_rate'),
                'optimal_sampling_rate_reasoning': seg.get('optimal_sampling_rate_reasoning', ''),
                'optimal_resolution': seg.get('optimal_resolution'),
                'optimal_resolution_reasoning': seg.get('optimal_resolution_reasoning', ''),
            })

    # Derive caption_type from filename
    fname = os.path.basename(path)
    caption_type = 'narration'
    if '_caption_' in fname:
        # e.g. "…_caption_narrations.json" → "narrations"
        part = fname.split('_caption_', 1)[-1]
        caption_type = part.replace('.json', '')

    return {
        'caption_type': caption_type,
        'captions': captions,
        'chunk_summaries': chunk_summaries,
        'human_review': data.get('human_review', {'status': 'pending'}),
        'metadata': {
            'video_id': data.get('video_id', ''),
            'video_path': data.get('video_path', ''),
            'duration': data.get('duration'),
            'start_time': data.get('start_time'),
        },
        # Preserve original chunks for round-trip save
        'chunks': data.get('chunks', []),
    }


def _save_caption_file(path: str, data: dict) -> None:
    """Persist caption data to disk."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _rebuild_chunks_from_captions(
    old_chunks: list,
    new_captions: list,
    chunk_summaries: list,
) -> list:
    """Rebuild chunk-based data from the flat edited captions list.

    This is the inverse of ``_normalise_caption_narrations``.  Each caption is
    assigned to the chunk whose time range contains the caption's start time.
    If a caption cannot be matched to any chunk, it is appended to the last
    chunk.

    The function preserves all original chunk-level metadata (video_id, paths,
    start_time, end_time, etc.) while replacing the ``segments`` with the
    updated caption data.
    """

    def _ts_to_seconds(ts: str) -> float:
        """Convert 'M:SS' or 'H:MM:SS' timestamp to seconds."""
        parts = ts.split(':')
        parts = [float(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] if parts else 0.0

    # Build time ranges for each chunk
    chunk_ranges = []
    for chunk in old_chunks:
        start = chunk.get('start_time', 0)
        end = chunk.get('end_time', float('inf'))
        chunk_ranges.append((start, end))

    # Build new chunks preserving original metadata
    new_chunks = []
    for i, chunk in enumerate(old_chunks):
        new_chunk = {k: v for k, v in chunk.items() if k != 'caption'}
        new_chunk['caption'] = {
            'overall_summary': '',
            'segments': [],
        }
        # Preserve existing summary
        old_caption = chunk.get('caption', {})
        if i < len(chunk_summaries) and chunk_summaries[i]:
            new_chunk['caption']['overall_summary'] = chunk_summaries[i]
        elif old_caption.get('overall_summary'):
            new_chunk['caption']['overall_summary'] = old_caption['overall_summary']
        new_chunks.append(new_chunk)

    # Assign each caption to the best-matching chunk
    for cap in new_captions:
        cap_start = _ts_to_seconds(cap.get('start', '0:00'))
        best_chunk_idx = len(new_chunks) - 1  # Default: last chunk
        for ci, (cs, ce) in enumerate(chunk_ranges):
            if cs <= cap_start < ce:
                best_chunk_idx = ci
                break

        # Convert flat caption back to segment format
        desc = cap.get('description', {})
        audio = desc.get('audio_transcript', [])
        if isinstance(audio, list):
            audio_out = [
                {'speaker': item.get('speaker'), 'transcript': item.get('transcript', '')}
                if isinstance(item, dict) else {'speaker': None, 'transcript': str(item)}
                for item in audio
            ]
        elif isinstance(audio, str) and audio.strip():
            audio_out = [{'speaker': None, 'transcript': audio}]
        else:
            audio_out = []

        people = desc.get('people', [])
        if isinstance(people, list):
            people_out = [
                {'person': item.get('person', ''), 'description': item.get('description', '')}
                if isinstance(item, dict) else {'person': '', 'description': str(item)}
                for item in people
            ]
        elif isinstance(people, str) and people.strip():
            people_out = [{'person': '', 'description': people}]
        else:
            people_out = []

        # Reconstruct objects – might have been joined with ', '
        objects_val = desc.get('objects', '')

        segment = {
            'time_span': {
                'start_time': cap.get('start', '0:00'),
                'end_time': cap.get('end', '0:00'),
            },
            'importance': cap.get('importance', 'medium'),
            'importance_reasoning': cap.get('importance_reasoning', ''),
            'confidence': cap.get('confidence', 'medium'),
            'confidence_reasoning': cap.get('confidence_reasoning', ''),
            'description': {
                'activities': desc.get('activities', '') or '',
                'environment': desc.get('environment', '') or '',
                'visible_text': desc.get('visible_text', '') or '',
                'objects': objects_val,
                'audio_transcript': audio_out,
                'people': people_out,
            },
        }

        # Preserve optional fields if present
        if cap.get('optimal_sampling_rate') is not None:
            segment['optimal_sampling_rate'] = cap['optimal_sampling_rate']
        if cap.get('optimal_sampling_rate_reasoning'):
            segment['optimal_sampling_rate_reasoning'] = cap['optimal_sampling_rate_reasoning']
        if cap.get('optimal_resolution') is not None:
            segment['optimal_resolution'] = cap['optimal_resolution']
        if cap.get('optimal_resolution_reasoning'):
            segment['optimal_resolution_reasoning'] = cap['optimal_resolution_reasoning']

        if 0 <= best_chunk_idx < len(new_chunks):
            new_chunks[best_chunk_idx]['caption']['segments'].append(segment)

    return new_chunks



def _caption_index_path() -> str:
    """Resolve caption index DB path."""
    configured = current_app.config.get('CAPTION_INDEX_DB')
    if configured:
        return str(configured)
    upload_folder = get_user_video_folder(current_app.config)
    return os.path.join(upload_folder, 'caption_index.db')


@caption_bp.route('/api/captions/<video_filename>')
def list_caption_files(video_filename):
    """List all caption files for a video."""
    try:
        safe_filename, video_dir = _safe_video_dir(video_filename)
        base_name = os.path.splitext(safe_filename)[0]

        caption_files = []
        if os.path.exists(video_dir):
            for fname in os.listdir(video_dir):
                is_legacy = fname.startswith(f"{base_name}_captions_") and fname.endswith('.json')
                is_v2 = fname.startswith(f"{base_name}_caption_") and fname.endswith('.json')
                if (is_legacy or is_v2):
                    fpath = os.path.join(video_dir, fname)
                    try:
                        data = _load_caption_file(fpath)
                        caption_files.append({
                            'filename': fname,
                            'caption_type': data.get('caption_type', ''),
                            'caption_count': len(data.get('captions', [])),
                            'human_review': data.get('human_review'),
                            'metadata': data.get('metadata', {}),
                            'chunk_summaries': data.get('chunk_summaries', []),
                        })
                    except Exception as exc:
                        logger.error("Error loading caption file %s: %s", fname, exc)

        return jsonify(caption_files)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("Error listing captions: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to load caption files'}), 500


@caption_bp.route('/api/search/captions')
def search_caption_index():
    """Search indexed caption segment descriptions by regex and/or semantic similarity."""
    try:
        args = parse_search_request_args(request.args)
        db_path = _caption_index_path()
        result = search_captions(
            db_path,
            args['query'],
            use_regex=args['use_regex'],
            use_semantic=args['use_semantic'],
            keys=args['keys'],
            page=args['page'],
            per_page=args['per_page'],
            semantic_limit=current_app.config.get('SEMANTIC_SEARCH_LIMIT', 5),
            semantic_threshold=current_app.config.get('SEMANTIC_SEARCH_THRESHOLD', 0.65),
        )
        return jsonify({'success': True, 'data': result})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Caption index not found'}), 404
    except re.error:
        return jsonify({'success': False, 'error': 'Invalid regex pattern'}), 400
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid search request'}), 400
    except Exception as exc:
        logger.error("Error searching caption index: %s", exc)
        return jsonify({'success': False, 'error': 'Failed to search captions'}), 500


@caption_bp.route('/api/captions/<video_filename>/<caption_filename>')
def get_caption_detail(video_filename, caption_filename):
    """Get full contents of a caption file."""
    try:
        _, video_dir = _safe_video_dir(video_filename)
        safe_caption = secure_filename(os.path.basename(caption_filename))
        if not safe_caption:
            return jsonify({'error': 'Invalid caption filename'}), 400

        path = _find_caption_file(video_dir, safe_caption)
        if not path:
            return jsonify({'error': 'Caption file not found'}), 404

        data = _load_caption_file(path)
        data['filename'] = safe_caption
        return jsonify(data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("Error loading caption detail: %s", exc)
        return jsonify({'error': 'Failed to load caption file'}), 500


@caption_bp.route('/api/captions/<video_filename>/<caption_filename>', methods=['PUT'])
@limiter.exempt
def update_caption_file(video_filename, caption_filename):
    """Update an entire caption file (captions list, human_review, etc.)."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        _, video_dir = _safe_video_dir(video_filename)
        safe_caption = secure_filename(os.path.basename(caption_filename))
        if not safe_caption:
            return jsonify({'error': 'Invalid caption filename'}), 400

        path = _find_caption_file(video_dir, safe_caption)
        if not path:
            return jsonify({'error': 'Caption file not found'}), 404

        payload = request.get_json() or {}
        existing = _load_caption_file(path)

        # Update allowed fields
        if 'captions' in payload:
            existing['captions'] = payload['captions']
            # When the file uses chunk-based format, rebuild chunks from the
            # updated flat captions so that the next load (which re-normalizes
            # from chunks) reflects the edits.
            if 'chunks' in existing:
                existing['chunks'] = _rebuild_chunks_from_captions(
                    existing['chunks'], payload['captions'],
                    existing.get('chunk_summaries', []))
        if 'human_review' in payload:
            existing['human_review'] = payload['human_review']
        if 'caption_type' in payload:
            existing['caption_type'] = payload['caption_type']
        if 'chunk_summaries' in payload:
            existing['chunk_summaries'] = payload['chunk_summaries']
            if 'chunks' in existing:
                for i, summary in enumerate(payload['chunk_summaries']):
                    if i < len(existing['chunks']):
                        if 'caption' not in existing['chunks'][i]:
                            existing['chunks'][i]['caption'] = {}
                        existing['chunks'][i]['caption']['overall_summary'] = summary
                # If fewer summaries were sent than chunks exist, clear removed summaries
                for i in range(len(payload['chunk_summaries']), len(existing['chunks'])):
                    if 'caption' in existing['chunks'][i]:
                        existing['chunks'][i]['caption']['overall_summary'] = ''

        _save_caption_file(path, existing)
        existing['filename'] = safe_caption
        return jsonify({'success': True, 'data': existing})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("Error updating caption file: %s", exc)
        return jsonify({'error': 'Failed to update caption file'}), 500


@caption_bp.route('/api/caption-files/<video_filename>', methods=['POST'])
@limiter.exempt
def create_caption_file(video_filename):
    """Create a new caption file for a video."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_filename, video_dir = _safe_video_dir(video_filename)
        base_name = os.path.splitext(safe_filename)[0]

        payload = request.get_json() or {}
        caption_type = payload.get('caption_type', 'narration')
        # Sanitize caption_type to be filesystem-safe
        safe_type = secure_filename(caption_type) or 'narration'

        timestamp_str = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        fname = f"{base_name}_captions_{safe_type}_{timestamp_str}.json"
        fpath = os.path.join(video_dir, fname)

        data = {
            'caption_type': caption_type,
            'captions': payload.get('captions', []),
            'human_review': {'status': 'pending'},
            'metadata': {
                'created_at': datetime.now(timezone.utc).isoformat(),
                'video_filename': safe_filename,
            }
        }
        _save_caption_file(fpath, data)
        data['filename'] = fname
        return jsonify({'success': True, 'data': data})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("Error creating caption file: %s", exc)
        return jsonify({'error': 'Failed to create caption file'}), 500


@caption_bp.route('/api/caption-files/<video_filename>/<caption_filename>', methods=['DELETE'])
@limiter.exempt
def delete_caption_file(video_filename, caption_filename):
    """Delete a caption file."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        _, video_dir = _safe_video_dir(video_filename)
        safe_caption = secure_filename(os.path.basename(caption_filename))
        if not safe_caption:
            return jsonify({'error': 'Invalid caption filename'}), 400

        path = _find_caption_file(video_dir, safe_caption)
        if not path:
            return jsonify({'error': 'Caption file not found'}), 404

        os.remove(path)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("Error deleting caption file: %s", exc)
        return jsonify({'error': 'Failed to delete caption file'}), 500
