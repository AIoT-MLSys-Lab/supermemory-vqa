"""
Routes responsible for annotation generation and CRUD.
"""
import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from annotation.service import VideoAnnotationService
from utils.validation import validate_annotation, sanitize_annotation

from ..config import get_user_video_folder
from ..extensions import limiter
from ..files import get_annotation_path
from ..security import extract_csrf_token, verify_csrf_token
from ..services import annotation_service, build_annotation_service

logger = logging.getLogger(__name__)
annotation_bp = Blueprint('annotations', __name__)


def _invalidate_video_cache():
    """Invalidate annotation cache in video routes when annotations are modified."""
    try:
        from .video_routes import _invalidate_annotation_cache
        _invalidate_annotation_cache()
    except ImportError:
        pass  # Cache invalidation is optional


def _is_annotation_file(filename: str, base_name: str) -> bool:
    """Check whether *filename* is an annotation JSON for *base_name*.

    Matches both the legacy ``{base}_annotations_*.json`` pattern **and** the
    new pipeline_v2 patterns ``{base}_verified_annotations.json`` and
    ``{base}_rejected_annotations.json``.
    """
    if not filename.endswith('.json'):
        return False
    if filename.startswith(f"{base_name}_annotations_"):
        return True
    if filename == f"{base_name}_verified_annotations.json":
        return True
    if filename == f"{base_name}_rejected_annotations.json":
        return True
    return False


def _normalise_v2_annotation_file(raw: dict) -> dict:
    """Normalise a pipeline_v2 annotation file into the frontend format.

    Both *verified* and *rejected* files contain an ``annotations`` list but
    with different shapes.  This helper normalises each entry into the flat
    ``Annotation`` structure the frontend already understands:

    * ``question`` (str)
    * ``answer`` (str)
    * ``skill``, ``room``, ``modalities``
    * ``time_span``, ``question_time_span``
    * ``answer_evidence``
    * ``location`` (bounding boxes)
    * ``human_review``

    Plus the new fields the frontend will learn to display:

    * ``question_details`` – the full question object (text, room, bounding_boxes, …)
    * ``answer_details`` – the full answer object (text, evidence_list, …)
    * ``verification_score`` – factual/objective scores, suggestions, etc.
    * ``annotation_type`` – ``"verified"`` or ``"rejected"``
    """
    file_review = raw.get('human_review', {})
    is_rejected = file_review.get('status') == 'rejected'
    annotation_type = 'rejected' if is_rejected else 'verified'

    normalised_annotations = []
    for entry in raw.get('annotations', []):
        # Rejected entries nest Q/A inside ``qa_pair``
        if 'qa_pair' in entry:
            qa = entry['qa_pair']
            q_obj = qa.get('question', {})
            a_obj = qa.get('answer', {})
            meta = qa.get('metadata', {})
        else:
            q_obj = entry.get('question', {})
            a_obj = entry.get('answer', {})
            meta = entry.get('metadata', {})

        v_score = entry.get('verification_score', meta.get('verification_score', {}))

        # Handle plural time_spans (current Stage 2) or legacy singular time_span
        q_spans_list = q_obj.get('time_spans', [])
        if not q_spans_list and 'time_span' in q_obj:
            # Fallback to singular but normalized to list
            q_spans_list = [q_obj['time_span']]
        
        question_time_spans = []
        for span in q_spans_list:
            question_time_spans.append({
                'start': span.get('start_time') or span.get('start') or '',
                'end': span.get('end_time') or span.get('end') or '',
            })

        # Backward compatibility for singular question_time_span
        question_time_span = question_time_spans[0] if question_time_spans else {'start': '', 'end': ''}

        # Convert answer evidence_list → answer_evidence (frontend shape)
        answer_evidence = []
        for ev in a_obj.get('evidence_list', []):
            # Support both singular time_span (common in evidence) or plural time_spans
            ev_spans_list = ev.get('time_spans', [])
            if not ev_spans_list and 'time_span' in ev:
                ev_spans_list = [ev['time_span']]
            
            ev_time_spans = []
            for span in ev_spans_list:
                ev_time_spans.append({
                    'start': span.get('start_time') or span.get('start') or '',
                    'end': span.get('end_time') or span.get('end') or '',
                })

            # Convert bounding boxes to frontend LocationBox format
            # Frontend expects Gemini format: [ymin, xmin, ymax, xmax] (normalized 0-1000)
            ev_boxes = []
            for bb in ev.get('bounding_boxes', []):
                ev_boxes.append({
                    'box_2d': [bb.get('ymin', 0), bb.get('xmin', 0),
                               bb.get('ymax', 0), bb.get('xmax', 0)],
                    'timestamp': bb.get('time_offset', ''),
                    'description': bb.get('label', ''),
                })
            v_id = ev.get('video_id') or ''
            if v_id and not v_id.endswith('.mp4'):
                v_id += '.mp4'
                
            answer_evidence.append({
                'time_spans': ev_time_spans,
                'video_path': v_id,
                'reason': ev.get('reason', ''),
                'room': ev.get('room', ''),
                'modalities': ev.get('modalities', []),
                'bounding_boxes': ev_boxes,
            })

        # Question bounding boxes → location.boxes (frontend shape)
        # Frontend expects Gemini format: [ymin, xmin, ymax, xmax] (normalized 0-1000)
        q_boxes = []
        for bb in q_obj.get('bounding_boxes', []):
            q_boxes.append({
                'box_2d': [bb.get('ymin', 0), bb.get('xmin', 0),
                           bb.get('ymax', 0), bb.get('xmax', 0)],
                'timestamp': bb.get('time_offset', ''),
                'description': bb.get('label', ''),
            })

        location = {'boxes': q_boxes} if q_boxes else None

        v_filename = q_obj.get('video_id', raw.get('video_id', ''))
        if v_filename and not v_filename.endswith('.mp4'):
            v_filename += '.mp4'

        # Extract answer choices from answer object
        answer_choices = []
        for choice in a_obj.get('answer_choices', []):
            answer_choices.append({
                'text': choice.get('text', ''),
                'choice_type': choice.get('choice_type', ''),
                'explanation': choice.get('explanation', ''),
            })

        ann = {
            'question': q_obj.get('text', ''),
            'answer': a_obj.get('text', ''),
            'skill': meta.get('skill', ''),
            'room': q_obj.get('room', ''),
            'modalities': q_obj.get('modalities', []),
            'question_time_spans': question_time_spans,
            'question_time_span': question_time_span,
            'time_span': question_time_span,
            'answer_evidence': answer_evidence,
            'location': location,
            'video_filename': v_filename,
            'human_review': entry.get('human_review') or (entry.get('qa_pair', {}).get('human_review') if 'qa_pair' in entry else None) or file_review,
            # --- new v2 fields ---
            'annotation_type': annotation_type,
            'question_details': q_obj,
            'answer_details': a_obj,
            'verification_score': v_score,
            'confidence': meta.get('confidence'),
            'confidence_reasoning': meta.get('confidence_reasoning', ''),
            # --- new answer choice fields ---
            'answer_choices': answer_choices,
            'is_answerable': a_obj.get('is_answerable', q_obj.get('is_answerable', True)),
        }
        normalised_annotations.append(ann)

    return {
        'annotations': normalised_annotations,
        'metadata': {
            'video_id': raw.get('video_id', ''),
            'annotation_type': annotation_type,
        },
        'human_review': file_review,
    }


def _load_annotation_file(filepath: str) -> dict:
    """Load an annotation file, normalising pipeline_v2 formats on the fly."""
    result = annotation_service.load_annotations(filepath)

    # Detect pipeline_v2 format: top-level 'video_id' key and structured
    # annotations with 'question' as dict or 'qa_pair' key.
    # Note: Sometimes the root 'video_id' might be missing if it's a merged file, 
    # so we check the entries.
    annotations = result.get('annotations', [])
    if annotations:
        first = annotations[0]
        is_v2 = (
            isinstance(first.get('question'), dict)
            or 'qa_pair' in first
            or 'question_details' in first # Already normalised
        )
        if is_v2:
            result = _normalise_v2_annotation_file(result)

    return result


def _denormalise_v2_annotation(ann: dict) -> dict:
    """Convert a normalised frontend Annotation object back to Stage 2 v2 schema.
    
    Reverse of _normalise_v2_annotation_file logic for a single entry.
    """
    # If it's already in v2 format (has qa_pair or question is dict), return as is
    # unless we want to sync updates from the flat fields.
    
    q_details = ann.get('question_details', {})
    a_details = ann.get('answer_details', {})
    
    # Sync flat fields to details if they exist
    if q_details:
        if 'question' in ann:
            q_details['text'] = ann['question']
        if 'room' in ann:
            q_details['room'] = ann['room']
        if 'modalities' in ann:
            q_details['modalities'] = ann['modalities']
        if 'question_time_spans' in ann and ann['question_time_spans']:
            q_details['time_spans'] = [
                {'start_time': ts.get('start', ''), 'end_time': ts.get('end', '')}
                for ts in ann['question_time_spans']
            ]
            # Sync singular for compatibility
            q_details['time_span'] = q_details['time_spans'][0]
        elif 'question_time_span' in ann:
            ts = ann['question_time_span']
            q_details['time_span'] = {
                'start_time': ts.get('start', ''),
                'end_time': ts.get('end', '')
            }
            q_details['time_spans'] = [q_details['time_span']]
        # Sync is_answerable field (now lives on answer)
        if 'is_answerable' in ann:
            q_details['is_answerable'] = ann['is_answerable']  # keep for backward compat

        # Sync boxes from location.boxes back to question.bounding_boxes
        location = ann.get('location') or {}
        if location.get('boxes'):
            q_boxes = []
            for box in location['boxes']:
                # Filter for question stream or untagged
                if box.get('stream', 'question') == 'question':
                    b2d = box.get('box_2d', [0, 0, 0, 0])
                    q_boxes.append({
                        'ymin': b2d[0], 'xmin': b2d[1],
                        'ymax': b2d[2], 'xmax': b2d[3],
                        'time_offset': box.get('timestamp', ''),
                        'label': box.get('description', '')
                    })
            q_details['bounding_boxes'] = q_boxes

    if a_details:
        if 'answer' in ann:
            a_details['text'] = ann['answer']

        # Sync answer_choices back to answer_details
        if 'answer_choices' in ann and ann['answer_choices']:
            answer_choices = []
            for choice in ann['answer_choices']:
                answer_choices.append({
                    'text': choice.get('text', ''),
                    'choice_type': choice.get('choice_type', ''),
                    'explanation': choice.get('explanation', ''),
                })
            a_details['answer_choices'] = answer_choices

        # Sync is_answerable to answer_details (canonical location)
        if 'is_answerable' in ann:
            a_details['is_answerable'] = ann['is_answerable']

        # Sync answer_evidence back to evidence_list
        if ann.get('answer_evidence'):
            evidence_list = []
            for ev in ann.get('answer_evidence') or []:
                # Evidence in v2 usually has its own time_span and bounding_boxes
                ev_ts = (ev.get('time_spans') or [{}])[0] if ev.get('time_spans') else {}
                
                ev_boxes = []
                for bb in ev.get('bounding_boxes', []):
                    b2d = bb.get('box_2d', [0, 0, 0, 0])
                    ev_boxes.append({
                        'ymin': b2d[0], 'xmin': b2d[1],
                        'ymax': b2d[2], 'xmax': b2d[3],
                        'time_offset': bb.get('timestamp', ''),
                        'label': bb.get('description', '')
                    })
                
                evidence_list.append({
                    'reason': ev.get('reason', ''),
                    'room': ev.get('room', ''),
                    'time_span': {
                        'start_time': ev_ts.get('start', ''),
                        'end_time': ev_ts.get('end', '')
                    } if ev_ts else None,
                    'time_spans': [
                        {'start_time': ts.get('start', ''), 'end_time': ts.get('end', '')}
                        for ts in (ev.get('time_spans') or [])
                    ],
                    'video_id': ev.get('video_path', '').removesuffix('.mp4'),
                    'modalities': ev.get('modalities', []),
                    'bounding_boxes': ev_boxes
                })
            a_details['evidence_list'] = evidence_list

    # Final structure based on annotation_type
    meta = {
        'skill': ann.get('skill', ''),
        'confidence': ann.get('confidence'),
        'confidence_reasoning': ann.get('confidence_reasoning', ''),
        'verification_score': ann.get('verification_score', {}),
        'primary_video_id': ann.get('video_filename', '').removesuffix('.mp4')
    }
    
    if ann.get('annotation_type') == 'rejected':
        return {
            'qa_pair': {
                'question': q_details,
                'answer': a_details,
                'metadata': meta
            },
            'verification_score': ann.get('verification_score', {}),
            'human_review': ann.get('human_review', {})
        }
    else:
        return {
            'question': q_details,
            'answer': a_details,
            'metadata': meta,
            'verification_score': ann.get('verification_score', {}),
            'human_review': ann.get('human_review', {})
        }

def _find_annotation_file(video_dir: str, annotations_folder: str, annotation_filename: str) -> str:
    """Search for an annotation file in known folders."""
    for candidate_dir in {video_dir, annotations_folder}:
        candidate_path = os.path.join(candidate_dir, annotation_filename)
        if os.path.exists(candidate_path):
            real_dir_path = Path(candidate_dir).resolve()
            real_path_obj = Path(candidate_path).resolve()
            if real_path_obj.is_relative_to(real_dir_path):
                return candidate_path
    return ''


@annotation_bp.route('/api/annotate', methods=['POST'])
@limiter.limit("5 per hour")
def annotate_video():
    """Generate annotations for a video with rate limiting."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on annotate")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    data = request.get_json() or {}
    video_filename = data.get('video_filename', '').strip()
    model_id = data.get('model_id', 'gemini-2.0-flash-exp')
    prompt_id = data.get('prompt_id', None)
    prompt_params = data.get('prompt_params', {})

    if not video_filename:
        return jsonify({'error': 'No video filename provided'}), 400

    try:
        safe_filename = secure_filename(os.path.basename(video_filename))
        if not safe_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_filename)

        if not os.path.exists(video_path):
            logger.warning("Video file not found: %s", safe_filename)
            return jsonify({'error': 'Video file not found'}), 404

        if not os.path.realpath(video_path).startswith(os.path.realpath(upload_folder)):
            logger.error("Path traversal attempt detected: %s", video_filename)
            return jsonify({'error': 'Invalid file path'}), 400

        service = build_annotation_service(model_id)
        logger.info("Starting annotation generation for: %s with model %s and prompt %s", safe_filename, model_id, prompt_id)
        result = service.annotate_video(video_path, prompt_id=prompt_id, **prompt_params)

        video_dir = os.path.dirname(video_path)
        base_name = os.path.splitext(safe_filename)[0]

        timestamp_str = result['metadata']['timestamp'].replace(':', '-').replace('.', '-')
        annotation_filename = f"{base_name}_annotations_{timestamp_str}.json"
        annotation_path = os.path.join(video_dir, annotation_filename)

        service.save_annotations(result, annotation_path)

        logger.info("Annotations saved successfully for: %s", safe_filename)
        return jsonify({
            'success': True,
            'result': result
        })
    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        return jsonify({'error': 'Invalid input'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error('Annotation generation failed: %s\n%s', exc, traceback.format_exc())
        return jsonify({'error': 'Failed to generate annotations. Please try again later.'}), 500


@annotation_bp.route('/api/annotations/<video_filename>')
def get_annotations(video_filename):
    """Get all annotation files for a video."""
    try:
        safe_filename = secure_filename(os.path.basename(video_filename))
        if not safe_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_filename)
        video_dir = os.path.dirname(video_path)
        base_name = os.path.splitext(safe_filename)[0]

        annotation_files = []
        search_dirs = {video_dir, current_app.config['ANNOTATIONS_FOLDER']}
        for directory in search_dirs:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    if _is_annotation_file(filename, base_name):
                        filepath = os.path.join(directory, filename)
                        try:
                            result = _load_annotation_file(filepath)
                            annotation_files.append({
                                'filename': filename,
                                'metadata': result.get('metadata', {}),
                                'annotation_count': len(result.get('annotations', []))
                            })
                        except Exception as exc:  # pragma: no cover - defensive logging
                            logger.error("Error loading annotation file %s: %s", filename, exc)

        return jsonify(annotation_files)
    except ValueError as exc:
        logger.error("Validation error in get_annotations: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error in get_annotations: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to load annotations'}), 500


@annotation_bp.route('/api/annotations/<video_filename>/<annotation_filename>')
def get_annotation_detail(video_filename, annotation_filename):
    """Get detailed annotations from a specific annotation file."""
    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))
        safe_annotation_filename = secure_filename(os.path.basename(annotation_filename))

        if not safe_video_filename or not safe_annotation_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)
        annotation_path = _find_annotation_file(
            video_dir,
            current_app.config['ANNOTATIONS_FOLDER'],
            safe_annotation_filename
        )

        if not annotation_path:
            return jsonify({'error': 'Annotation file not found'}), 404

        result = _load_annotation_file(annotation_path)

        if 'annotations' in result:
            result['annotations'] = [sanitize_annotation(ann) for ann in result['annotations']]

        # Include the annotation filename in response so frontend can track it
        result['annotation_filename'] = safe_annotation_filename

        return jsonify(result)
    except ValueError as exc:
        logger.error("Invalid filename in get_annotation_detail: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400


@annotation_bp.route('/api/annotations/<video_filename>/<annotation_filename>/<int:index>', methods=['PUT'])
def update_annotation(video_filename, annotation_filename, index):
    """Update a specific annotation with validation and commit to disk."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on update")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))
        safe_annotation_filename = secure_filename(os.path.basename(annotation_filename))

        if not safe_video_filename or not safe_annotation_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)
        annotation_path = _find_annotation_file(
            video_dir,
            current_app.config['ANNOTATIONS_FOLDER'],
            safe_annotation_filename
        )

        if not annotation_path or not os.path.exists(annotation_path):
            return jsonify({'error': 'Annotations not found'}), 404

        annotation_data = annotation_service.load_annotations(annotation_path)
        annotations = annotation_data.get('annotations', [])

        if index < 0 or index >= len(annotations):
            return jsonify({'error': 'Invalid annotation index'}), 400

        updated_data = request.get_json() or {}

        if not validate_annotation(updated_data):
            # If standard validation fails, check if it's a v2 annotation which has a different schema
            # We trust the frontend if it includes v2 specific fields
            is_v2_input = 'question_details' in updated_data or 'answer_details' in updated_data
            if not is_v2_input:
                logger.warning("Invalid annotation data on update: %s", updated_data)
                return jsonify({'error': 'Invalid annotation data. Check required fields and types.'}), 400

        # If it was originally v2, or the input is v2, denormalise before saving
        original_is_v2 = (
            annotations and (
                isinstance(annotations[0].get('question'), dict) 
                or 'qa_pair' in annotations[0]
            )
        )
        
        if original_is_v2:
            save_data = _denormalise_v2_annotation(updated_data)
        else:
            save_data = updated_data

        annotations[index] = save_data
        annotation_data['annotations'] = annotations

        # Save to disk
        annotation_service.save_annotations(annotation_data, annotation_path)

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation updated and saved to disk: %s index %s in %s", video_filename, index, annotation_path)
        return jsonify({'success': True, 'annotation': updated_data})
    except ValueError as exc:
        logger.error("Validation error on update: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Update error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Update failed'}), 500


@annotation_bp.route('/api/annotations/<video_filename>/<annotation_filename>/<int:index>', methods=['DELETE'])
def delete_annotation(video_filename, annotation_filename, index):
    """Delete a specific annotation."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on delete")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))
        safe_annotation_filename = secure_filename(os.path.basename(annotation_filename))

        if not safe_video_filename or not safe_annotation_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)
        annotation_path = _find_annotation_file(
            video_dir,
            current_app.config['ANNOTATIONS_FOLDER'],
            safe_annotation_filename
        )

        if not annotation_path or not os.path.exists(annotation_path):
            return jsonify({'error': 'Annotations not found'}), 404

        annotation_data = annotation_service.load_annotations(annotation_path)
        annotations = annotation_data.get('annotations', [])

        if index < 0 or index >= len(annotations):
            return jsonify({'error': 'Invalid annotation index'}), 400

        deleted = annotations.pop(index)
        annotation_data['annotations'] = annotations

        # Save to disk
        annotation_service.save_annotations(annotation_data, annotation_path)

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation deleted and saved to disk: %s index %s in %s", video_filename, index, annotation_path)
        return jsonify({'success': True, 'deleted': sanitize_annotation(deleted)})
    except ValueError as exc:
        logger.error("Validation error on delete: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Delete error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Delete failed'}), 500


@annotation_bp.route('/api/annotations/<video_filename>/<annotation_filename>/add', methods=['POST'])
def add_annotation(video_filename, annotation_filename):
    """Add a new annotation to an existing annotation file."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on add")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))
        safe_annotation_filename = secure_filename(os.path.basename(annotation_filename))

        if not safe_video_filename or not safe_annotation_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)
        annotation_path = _find_annotation_file(
            video_dir,
            current_app.config['ANNOTATIONS_FOLDER'],
            safe_annotation_filename
        )

        if not annotation_path or not os.path.exists(annotation_path):
            return jsonify({'error': 'Annotation file not found'}), 404

        new_annotation = request.get_json() or {}

        if not validate_annotation(new_annotation):
            is_v2_input = 'question_details' in new_annotation or 'answer_details' in new_annotation
            if not is_v2_input:
                logger.warning("Invalid annotation data on add: %s", new_annotation)
                return jsonify({'error': 'Invalid annotation data. Check required fields and types.'}), 400

        annotation_data = annotation_service.load_annotations(annotation_path)
        annotations = annotation_data.get('annotations', [])
        
        original_is_v2 = (
            annotations and (
                isinstance(annotations[0].get('question'), dict) 
                or 'qa_pair' in annotations[0]
            )
        )
        
        if original_is_v2:
            save_data = _denormalise_v2_annotation(new_annotation)
        else:
            save_data = new_annotation

        annotations.append(save_data)
        annotation_data['annotations'] = annotations

        # Save to disk
        annotation_service.save_annotations(annotation_data, annotation_path)

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation added and saved to disk: %s in %s", video_filename, annotation_path)
        return jsonify({'success': True, 'annotation': new_annotation, 'index': len(annotations) - 1})
    except ValueError as exc:
        logger.error("Validation error on add: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Add annotation error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to add annotation'}), 500


@annotation_bp.route('/api/annotation-files/<video_filename>/<annotation_filename>', methods=['DELETE'])
def delete_annotation_file(video_filename, annotation_filename):
    """Delete an entire annotation file."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on file delete")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))
        safe_annotation_filename = secure_filename(os.path.basename(annotation_filename))

        if not safe_video_filename or not safe_annotation_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)
        annotation_path = _find_annotation_file(
            video_dir,
            current_app.config['ANNOTATIONS_FOLDER'],
            safe_annotation_filename
        )

        if not annotation_path or not os.path.exists(annotation_path):
            return jsonify({'error': 'Annotation file not found'}), 404

        os.remove(annotation_path)

        # Invalidate cache since annotation file was deleted
        _invalidate_video_cache()

        logger.info("Annotation file deleted: %s", annotation_path)
        return jsonify({'success': True, 'deleted_file': safe_annotation_filename})
    except ValueError as exc:
        logger.error("Validation error on file delete: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Delete file error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to delete annotation file'}), 500


@annotation_bp.route('/api/annotation-files/<video_filename>', methods=['POST'])
def create_annotation_file(video_filename):
    """Create a new annotation file for a video from scratch."""
    csrf_token = extract_csrf_token(request)
    if not verify_csrf_token(csrf_token):
        logger.warning("CSRF token validation failed on file create")
        return jsonify({'error': 'Invalid CSRF token'}), 403

    try:
        safe_video_filename = secure_filename(os.path.basename(video_filename))

        if not safe_video_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_video_filename)
        video_dir = os.path.dirname(video_path)

        # Generate filename with timestamp
        base_name = os.path.splitext(safe_video_filename)[0]
        timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
        annotation_filename = f"{base_name}_annotations_{timestamp_str}.json"
        annotation_path = os.path.join(video_dir or upload_folder, annotation_filename)

        # Create empty annotation data structure
        annotation_data = {
            'annotations': [],
            'metadata': {
                'model': 'manual',
                'prompt_id': 'manual',
                'prompt_name': 'Manual Entry',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'video_filename': safe_video_filename,
                'prompt_parameters': {}
            }
        }

        # Save to disk
        annotation_service.save_annotations(annotation_data, annotation_path)

        # Invalidate cache since new annotation file was created
        _invalidate_video_cache()

        logger.info("New annotation file created: %s", annotation_path)
        return jsonify({
            'success': True,
            'filename': annotation_filename,
            'metadata': annotation_data['metadata']
        })
    except ValueError as exc:
        logger.error("Validation error on file create: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Create file error: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to create annotation file'}), 500


@annotation_bp.route('/api/summary/<video_filename>')
def get_summary(video_filename):
    """Get a summary of all annotations for a video including review status."""
    try:
        safe_filename = secure_filename(os.path.basename(video_filename))
        if not safe_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Get the video folder for current user (may be per-session in multi-user mode)
        upload_folder = get_user_video_folder(current_app.config)
        video_path = os.path.join(upload_folder, safe_filename)
        video_dir = os.path.dirname(video_path)
        base_name = os.path.splitext(safe_filename)[0]

        summary = {
            'video_filename': safe_filename,
            'annotation_files': [],
            'total_annotations': 0,
            'reviewed_count': 0,
            'pending_count': 0,
            'skills_breakdown': {},
            'annotations': []
        }

        search_dirs = {video_dir, current_app.config['ANNOTATIONS_FOLDER']}
        for directory in search_dirs:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    if _is_annotation_file(filename, base_name):
                        filepath = os.path.join(directory, filename)
                        try:
                            result = _load_annotation_file(filepath)
                            annotations = result.get('annotations', [])
                            meta = result.get('metadata', {})

                            file_summary = {
                                'filename': filename,
                                'metadata': meta,
                                'annotation_count': len(annotations),
                                'reviewed_count': 0,
                                'pending_count': 0
                            }

                            for ann in annotations:
                                summary['total_annotations'] += 1

                                # Check human review status
                                human_review = ann.get('human_review', {})
                                is_reviewed = human_review.get('reviewed', False)

                                if is_reviewed:
                                    summary['reviewed_count'] += 1
                                    file_summary['reviewed_count'] += 1
                                else:
                                    summary['pending_count'] += 1
                                    file_summary['pending_count'] += 1

                                # Track skills breakdown
                                skill = ann.get('skill', '')
                                if skill not in summary['skills_breakdown']:
                                    summary['skills_breakdown'][skill] = 0
                                summary['skills_breakdown'][skill] += 1

                                # Add annotation summary with review status
                                review_status = human_review.get('status', 'pending')
                                if is_reviewed and review_status == 'pending':
                                    # Legacy reviewed annotations without status
                                    review_status = 'accepted'
                                summary['annotations'].append({
                                    'file': filename,
                                    'question': ann.get('question', ''),
                                    'skill': skill,
                                    'reviewed': is_reviewed,
                                    'review_status': review_status,
                                    'review_comment': human_review.get('comment', ''),
                                    'time_span': ann.get('time_span', {})
                                })

                            summary['annotation_files'].append(file_summary)
                        except Exception as exc:  # pragma: no cover - defensive logging
                            logger.error("Error loading annotation file %s: %s", filename, exc)

        return jsonify(summary)
    except ValueError as exc:
        logger.error("Validation error in get_summary: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error in get_summary: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to get summary'}), 500
