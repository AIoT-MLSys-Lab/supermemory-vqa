"""
Routes responsible for annotation generation and CRUD.
"""
import json
import logging
import os
import tempfile
import traceback
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from annotation.service import VideoAnnotationService
from utils.validation import parse_timestamp, validate_annotation, validate_timestamp, sanitize_annotation

from ..config import get_user_video_folder
from ..extensions import limiter
from ..files import get_annotation_path
from ..security import extract_csrf_token, verify_csrf_token
from ..services import annotation_service, build_annotation_service

logger = logging.getLogger(__name__)
annotation_bp = Blueprint('annotations', __name__)


class AnnotationLockUnavailable(RuntimeError):
    """Raised when annotation writes cannot be protected by the file lock."""


def _invalidate_video_cache():
    """Invalidate annotation cache in video routes when annotations are modified."""
    try:
        from .video_routes import _invalidate_annotation_cache
        _invalidate_annotation_cache()
    except ImportError:
        pass  # Cache invalidation is optional


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _file_revision(document: dict) -> int:
    metadata = _as_dict(document.get('metadata'))
    try:
        return int(metadata.get('revision', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _set_file_revision(document: dict, revision: int) -> None:
    metadata = _as_dict(document.get('metadata')).copy()
    metadata['revision'] = revision
    document['metadata'] = metadata


def _annotation_id_from(annotation: dict) -> str:
    if not isinstance(annotation, dict):
        return ''
    direct = annotation.get('annotation_id')
    if direct:
        return str(direct)

    metadata_details = _as_dict(annotation.get('metadata_details'))
    for key in ('qa_id', 'annotation_id'):
        if metadata_details.get(key):
            return str(metadata_details[key])

    metadata = _as_dict(annotation.get('metadata'))
    for key in ('qa_id', 'annotation_id'):
        if metadata.get(key):
            return str(metadata[key])

    qa_pair = _as_dict(annotation.get('qa_pair'))
    qa_metadata = _as_dict(qa_pair.get('metadata'))
    for key in ('qa_id', 'annotation_id'):
        if qa_metadata.get(key):
            return str(qa_metadata[key])
    return ''


def _ensure_annotation_id(annotation: dict, preferred: str = '') -> str:
    annotation_id = _annotation_id_from(annotation) or preferred or str(uuid.uuid4())
    annotation['annotation_id'] = annotation_id
    metadata_details = _as_dict(annotation.get('metadata_details'))
    if metadata_details or annotation.get('question_details') or annotation.get('answer_details'):
        metadata_details = metadata_details.copy()
        metadata_details.setdefault('qa_id', annotation_id)
        annotation['metadata_details'] = metadata_details
    return annotation_id


def _is_pipeline_v2_document(document: dict) -> bool:
    annotations = document.get('annotations', [])
    if not annotations or not isinstance(annotations[0], dict):
        return False
    first = annotations[0]
    return isinstance(first.get('question'), dict) or 'qa_pair' in first


def _read_annotation_document_unlocked(annotation_path: str) -> dict:
    if not os.path.exists(annotation_path):
        return {'annotations': [], 'metadata': {}}
    with open(annotation_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return {'annotations': data, 'metadata': {'model': 'unknown', 'prompt_id': 'legacy'}}
    if not isinstance(data, dict):
        return {'annotations': [], 'metadata': {}}
    data.setdefault('annotations', [])
    data['metadata'] = _as_dict(data.get('metadata')).copy()
    data['metadata'].setdefault('revision', 0)
    return data


def _write_annotation_document_unlocked(annotation_path: str, document: dict) -> None:
    output_dir = os.path.dirname(annotation_path) or '.'
    os.makedirs(output_dir, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                'w',
                encoding='utf-8',
                dir=output_dir,
                prefix=f".{os.path.basename(annotation_path)}.",
                suffix='.tmp',
                delete=False) as tmp_file:
            tmp_path = tmp_file.name
            json.dump(document, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.write('\n')
        os.replace(tmp_path, annotation_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Failed to remove temporary annotation file: %s", tmp_path)


def _locked_annotation_mutation(annotation_path: str, mutator):
    try:
        from visualization.filelock import write_lock
        lock = write_lock(annotation_path)
    except ImportError as exc:
        raise AnnotationLockUnavailable("File locking is unavailable; refusing unsafe annotation write") from exc

    with lock:
        document = _read_annotation_document_unlocked(annotation_path)
        current_revision = _file_revision(document)
        mutation = mutator(document, current_revision)
        if mutation.get('save', True):
            next_revision = current_revision + 1
            _set_file_revision(document, next_revision)
            _write_annotation_document_unlocked(annotation_path, document)
            mutation['file_revision'] = next_revision
        else:
            mutation.setdefault('file_revision', current_revision)
        mutation['document'] = document
        return mutation


def _normalise_annotation_from_document(document: dict, index: int) -> dict:
    annotations = document.get('annotations', [])
    if index < 0 or index >= len(annotations) or not isinstance(annotations[index], dict):
        return {}
    if _is_pipeline_v2_document(document):
        subset = deepcopy(document)
        subset['annotations'] = [deepcopy(annotations[index])]
        normalised = _normalise_v2_annotation_file(subset).get('annotations', [])
        return normalised[0] if normalised else {}
    return deepcopy(annotations[index])


def _transient_annotation_id(annotation: dict, annotation_filename: str, index: int) -> str:
    return _annotation_id_from(annotation) or f"legacy:{annotation_filename}:{index}"


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
        if not isinstance(entry, dict):
            continue
        # Rejected entries nest Q/A inside ``qa_pair``
        if 'qa_pair' in entry:
            qa = _as_dict(entry['qa_pair'])
            q_obj = _as_dict(qa.get('question'))
            a_obj = _as_dict(qa.get('answer'))
            meta = _as_dict(qa.get('metadata'))
        else:
            q_obj = _as_dict(entry.get('question'))
            a_obj = _as_dict(entry.get('answer'))
            meta = _as_dict(entry.get('metadata'))

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
                'video_id': span.get('video_id') or q_obj.get('video_id') or '',
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
                    'video_id': span.get('video_id') or ev.get('video_id') or '',
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

        annotation_id = meta.get('qa_id') or meta.get('annotation_id') or entry.get('annotation_id', '')
        if not annotation_id and 'qa_pair' in entry:
            annotation_id = qa.get('annotation_id', '')
        schema_version = (
            raw.get('schema_version')
            or _as_dict(raw.get('metadata')).get('schema_version')
            or meta.get('schema_version')
            or 'pipeline_v2'
        )

        # Extract answer choices from answer object
        answer_choices = []
        for choice in a_obj.get('answer_choices', []):
            answer_choices.append({
                'text': choice.get('text', ''),
                'choice_type': choice.get('choice_type', ''),
                'explanation': choice.get('explanation', ''),
            })

        ann = {
            'annotation_id': annotation_id,
            'schema_version': schema_version,
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
            'metadata_details': deepcopy(meta),
            'verification_score': v_score,
            'confidence': meta.get('confidence'),
            'confidence_reasoning': meta.get('confidence_reasoning', ''),
            'balance_reasoning': a_obj.get('balance_reasoning', entry.get('balance_reasoning', '')),
            'rejection_reason': entry.get('rejection_reason') or _as_dict(entry.get('qa_pair')).get('rejection_reason', ''),
            # --- new answer choice fields ---
            'answer_choices': answer_choices,
            'is_answerable': a_obj.get('is_answerable', q_obj.get('is_answerable', True)),
        }
        normalised_annotations.append(ann)

    return {
        'annotations': normalised_annotations,
        'metadata': {
            **_as_dict(raw.get('metadata')),
            'video_id': raw.get('video_id', _as_dict(raw.get('metadata')).get('video_id', '')),
            'annotation_type': annotation_type,
            'revision': _file_revision(raw),
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
        is_v2 = isinstance(first.get('question'), dict) or 'qa_pair' in first
        if is_v2:
            result = _normalise_v2_annotation_file(result)

    return result


def _denormalise_v2_annotation(ann: dict) -> dict:
    """Convert a normalised frontend Annotation object back to Stage 2 v2 schema.
    
    Reverse of _normalise_v2_annotation_file logic for a single entry.
    """
    q_details = deepcopy(_as_dict(ann.get('question_details')))
    a_details = deepcopy(_as_dict(ann.get('answer_details')))
    
    # Sync flat fields to details if they exist
    if 'question' in ann:
        q_details['text'] = ann['question']
    if 'room' in ann:
        q_details['room'] = ann['room']
    if 'modalities' in ann:
        q_details['modalities'] = ann['modalities']
    if 'question_time_spans' in ann and ann['question_time_spans']:
        q_details['time_spans'] = [
            {'start_time': ts.get('start', ''), 'end_time': ts.get('end', ''), 'video_id': ts.get('video_id', '')}
            for ts in ann['question_time_spans']
        ]
        q_details['time_span'] = q_details['time_spans'][0]
    elif 'question_time_span' in ann:
        ts = _as_dict(ann.get('question_time_span'))
        q_details['time_span'] = {
            'start_time': ts.get('start', ''),
            'end_time': ts.get('end', ''),
            'video_id': ts.get('video_id', '')
        }
        q_details['time_spans'] = [q_details['time_span']]
    if 'is_answerable' in ann:
        q_details['is_answerable'] = ann['is_answerable']  # keep for backward compat

    location = _as_dict(ann.get('location'))
    if location.get('boxes'):
        q_boxes = []
        for box in location['boxes']:
            if not isinstance(box, dict):
                continue
            if box.get('stream', 'question') == 'question':
                b2d = box.get('box_2d', [0, 0, 0, 0])
                q_boxes.append({
                    'ymin': b2d[0], 'xmin': b2d[1],
                    'ymax': b2d[2], 'xmax': b2d[3],
                    'time_offset': box.get('timestamp', ''),
                    'label': box.get('description', '')
                })
        q_details['bounding_boxes'] = q_boxes

    if 'answer' in ann:
        a_details['text'] = ann['answer']

    if 'answer_choices' in ann:
        existing_choices = a_details.get('answer_choices') or []
        answer_choices = []
        for index, choice in enumerate(ann.get('answer_choices') or []):
            prior = deepcopy(existing_choices[index]) if index < len(existing_choices) and isinstance(existing_choices[index], dict) else {}
            prior.update({
                'text': choice.get('text', ''),
                'choice_type': choice.get('choice_type', ''),
                'explanation': choice.get('explanation', ''),
            })
            answer_choices.append(prior)
        a_details['answer_choices'] = answer_choices

    if 'is_answerable' in ann:
        a_details['is_answerable'] = ann['is_answerable']
    if 'balance_reasoning' in ann:
        a_details['balance_reasoning'] = ann.get('balance_reasoning', '')

    if 'answer_evidence' in ann:
        existing_evidence = a_details.get('evidence_list') or []
        evidence_list = []
        for index, ev in enumerate(ann.get('answer_evidence') or []):
            if not isinstance(ev, dict):
                continue
            prior = deepcopy(existing_evidence[index]) if index < len(existing_evidence) and isinstance(existing_evidence[index], dict) else {}
            ev_ts = (ev.get('time_spans') or [{}])[0] if ev.get('time_spans') else {}

            ev_boxes = []
            for bb in ev.get('bounding_boxes', []):
                if not isinstance(bb, dict):
                    continue
                b2d = bb.get('box_2d', [0, 0, 0, 0])
                ev_boxes.append({
                    'ymin': b2d[0], 'xmin': b2d[1],
                    'ymax': b2d[2], 'xmax': b2d[3],
                    'time_offset': bb.get('timestamp', ''),
                    'label': bb.get('description', '')
                })

            video_id = ev.get('video_path', '').removesuffix('.mp4')
            prior.update({
                'reason': ev.get('reason', ''),
                'room': ev.get('room', ''),
                'time_span': {
                    'start_time': ev_ts.get('start', ''),
                    'end_time': ev_ts.get('end', '')
                } if ev_ts else prior.get('time_span'),
                'time_spans': [
                    {
                        'start_time': ts.get('start', ''),
                        'end_time': ts.get('end', ''),
                        'video_id': ts.get('video_id', video_id),
                    }
                    for ts in (ev.get('time_spans') or [])
                ],
                'video_id': video_id,
                'modalities': ev.get('modalities', []),
                'bounding_boxes': ev_boxes
            })
            evidence_list.append(prior)
        a_details['evidence_list'] = evidence_list

    # Final structure based on annotation_type
    meta = deepcopy(_as_dict(ann.get('metadata_details')))
    annotation_id = ann.get('annotation_id') or meta.get('qa_id') or meta.get('annotation_id')
    if annotation_id:
        meta.setdefault('qa_id', annotation_id)
    if 'skill' in ann:
        meta['skill'] = ann.get('skill', '')
    if 'confidence' in ann:
        meta['confidence'] = ann.get('confidence')
    if 'confidence_reasoning' in ann:
        meta['confidence_reasoning'] = ann.get('confidence_reasoning', '')
    if 'verification_score' in ann:
        meta['verification_score'] = ann.get('verification_score', {})
    if ann.get('video_filename') and not meta.get('primary_video_id'):
        meta['primary_video_id'] = ann.get('video_filename', '').removesuffix('.mp4')
    
    if ann.get('annotation_type') == 'rejected':
        result = {
            'qa_pair': {
                'question': q_details,
                'answer': a_details,
                'metadata': meta
            },
            'verification_score': ann.get('verification_score', {}),
            'human_review': ann.get('human_review', {})
        }
        if ann.get('rejection_reason'):
            result['rejection_reason'] = ann.get('rejection_reason')
        return result
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


def _annotation_base_name(filename: str) -> str:
    """Return the source video base name for a supported annotation file."""
    if filename.endswith('_verified_annotations.json'):
        return filename.removesuffix('_verified_annotations.json')
    if filename.endswith('_rejected_annotations.json'):
        return filename.removesuffix('_rejected_annotations.json')
    if '_annotations_' in filename and filename.endswith('.json'):
        return filename.split('_annotations_', 1)[0]
    return ''


def _find_video_filename_for_base(video_folder: str, base_name: str) -> str:
    """Find a matching video filename in *video_folder* for an annotation base."""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'mp4', 'avi', 'mov', 'mkv', 'webm'})
    try:
        for filename in os.listdir(video_folder):
            stem, ext = os.path.splitext(filename)
            if stem == base_name and ext.lstrip('.').lower() in allowed_extensions:
                return filename
    except OSError:
        logger.warning("Could not scan video folder for base %s", base_name)
    return f"{base_name}.mp4"


def _validation_response(error: str, details=None):
    payload = {'success': False, 'code': 'validation_error', 'error': error}
    if details:
        payload['details'] = details
    return jsonify(payload), 400


def _conflict_response(error: str, current: dict, file_revision: int):
    return jsonify({
        'success': False,
        'code': 'conflict',
        'error': error,
        'current': current,
        'file_revision': file_revision,
    }), 409


def _extract_update_source(annotation: dict) -> tuple[dict, int | None, str, bool]:
    has_source_contract = '_source' in annotation or 'file_revision' in annotation or isinstance(annotation.get('source'), dict)
    source = _as_dict(annotation.pop('_source', None))
    if 'source' in annotation and isinstance(annotation.get('source'), dict):
        source.update(annotation.pop('source'))
    file_revision = source.get('file_revision', annotation.pop('file_revision', None))
    try:
        file_revision = int(file_revision) if file_revision is not None else None
    except (TypeError, ValueError):
        file_revision = None
    annotation_id = source.get('annotation_id') or annotation.get('annotation_id') or ''
    return annotation, file_revision, str(annotation_id) if annotation_id else '', has_source_contract


def _validate_span_pair(span: dict, label: str, errors: list[str]) -> None:
    start = (span.get('start') or span.get('start_time') or '').strip()
    end = (span.get('end') or span.get('end_time') or '').strip()
    if not start and not end:
        return
    if not validate_timestamp(start):
        errors.append(f"{label} start time must use M:SS or H:MM:SS format")
        return
    if not validate_timestamp(end):
        errors.append(f"{label} end time must use M:SS or H:MM:SS format")
        return
    if parse_timestamp(start) > parse_timestamp(end):
        errors.append(f"{label} start time must be before or equal to end time")


def _validate_review_annotation(annotation: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(annotation, dict):
        return ['Annotation payload must be an object']

    is_review_shape = bool(
        annotation.get('annotation_type')
        or annotation.get('question_details')
        or annotation.get('answer_details')
        or 'answer_choices' in annotation
    )
    if is_review_shape:
        if not str(annotation.get('question') or '').strip():
            errors.append('Question text is required')
        if not str(annotation.get('answer') or '').strip():
            errors.append('Answer text is required')
        skill = annotation.get('skill') or _as_dict(annotation.get('metadata_details')).get('skill')
        if not str(skill or '').strip():
            errors.append('Skill is required')

        choices = annotation.get('answer_choices')
        if not isinstance(choices, list) or not choices:
            errors.append('At least one answer choice is required')
        else:
            types = [choice.get('choice_type') for choice in choices if isinstance(choice, dict)]
            if annotation.get('is_answerable') is False:
                if any(choice_type != 'incorrect' for choice_type in types):
                    errors.append('Unanswerable QAs must mark all answer choices as incorrect')
            else:
                if types.count('correct') != 1 or types.count('vague') != 1 or types.count('incorrect') != 1:
                    errors.append('Answerable QAs must have exactly one correct, one vague, and one incorrect choice')
                correct_choice = next((choice for choice in choices if isinstance(choice, dict) and choice.get('choice_type') == 'correct'), None)
                if correct_choice and correct_choice.get('text') != annotation.get('answer'):
                    errors.append('Correct answer choice text must match the answer text')

    question_spans = annotation.get('question_time_spans') or []
    if not question_spans and annotation.get('question_time_span'):
        question_spans = [annotation['question_time_span']]
    if not question_spans and annotation.get('time_span'):
        question_spans = [annotation['time_span']]
    for idx, span in enumerate(question_spans):
        if isinstance(span, dict):
            _validate_span_pair(span, f"Question span {idx + 1}", errors)

    for evidence_idx, evidence in enumerate(annotation.get('answer_evidence') or []):
        if not isinstance(evidence, dict):
            continue
        for span_idx, span in enumerate(evidence.get('time_spans') or []):
            if isinstance(span, dict):
                _validate_span_pair(span, f"Evidence {evidence_idx + 1}.{span_idx + 1}", errors)
    return errors


@annotation_bp.route('/api/qa-review')
def get_qa_review_items():
    """Return a single review queue of QAs across the current video folder."""
    try:
        upload_folder = get_user_video_folder(current_app.config)
        resolved_upload_folder = Path(upload_folder).resolve()
        annotations_folder = Path(current_app.config['ANNOTATIONS_FOLDER']).resolve()
        search_dirs = []
        for directory in (resolved_upload_folder, annotations_folder):
            if directory not in search_dirs:
                search_dirs.append(directory)

        items = []
        seen_files = set()
        for directory in search_dirs:
            if not directory.exists() or not directory.is_dir():
                continue
            for filename in os.listdir(directory):
                base_name = _annotation_base_name(filename)
                if not base_name:
                    continue
                filepath = (directory / filename).resolve()
                if str(filepath) in seen_files:
                    continue
                seen_files.add(str(filepath))
                if not filepath.is_file() or not filepath.is_relative_to(directory):
                    continue

                try:
                    result = _load_annotation_file(str(filepath))
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error("Skipping malformed annotation file %s: %s", filepath, exc)
                    continue

                annotations = result.get('annotations', [])
                if not isinstance(annotations, list):
                    logger.warning("Skipping annotation file with non-list annotations: %s", filepath)
                    continue

                video_filename = _find_video_filename_for_base(str(resolved_upload_folder), base_name)
                metadata = result.get('metadata', {}) or {}
                annotation_type = metadata.get('annotation_type', 'legacy')
                file_revision = _file_revision(result)
                for index, annotation in enumerate(annotations):
                    if not isinstance(annotation, dict):
                        continue
                    clean_annotation = sanitize_annotation(annotation)
                    clean_annotation['annotation_id'] = _transient_annotation_id(clean_annotation, filename, index)
                    clean_annotation.setdefault('video_filename', video_filename)
                    items.append({
                        'id': f"{video_filename}:{filename}:{index}",
                        'video_filename': video_filename,
                        'annotation_filename': filename,
                        'annotation_index': index,
                        'annotation': clean_annotation,
                        'source': {
                            'annotation_type': clean_annotation.get('annotation_type', annotation_type),
                            'video_id': metadata.get('video_id') or base_name,
                            'file_path': str(filepath),
                            'file_revision': file_revision,
                        },
                    })

        return jsonify({'items': items, 'count': len(items)})
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error loading QA review queue: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to load QA review queue'}), 500


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
            result['annotations'] = [
                {
                    **sanitize_annotation(ann),
                    'annotation_id': _transient_annotation_id(ann, safe_annotation_filename, index),
                }
                for index, ann in enumerate(result['annotations'])
            ]

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

        updated_data, expected_revision, expected_annotation_id, has_source_contract = _extract_update_source(deepcopy(request.get_json() or {}))
        if has_source_contract and expected_revision is None:
            return _validation_response('file_revision is required for annotation updates')

        validation_errors = _validate_review_annotation(updated_data)
        if validation_errors:
            return _validation_response('Invalid annotation data', validation_errors)

        if not validate_annotation(deepcopy(updated_data)):
            is_v2_input = 'question_details' in updated_data or 'answer_details' in updated_data
            if not is_v2_input:
                logger.warning("Invalid annotation data on update: %s", updated_data)
                return _validation_response('Invalid annotation data. Check required fields and types.')

        def mutate(document: dict, current_revision: int) -> dict:
            annotations = document.get('annotations', [])
            if index < 0 or index >= len(annotations):
                return {'save': False, 'status': 'validation_error', 'error': 'Invalid annotation index'}

            current_annotation = sanitize_annotation(_normalise_annotation_from_document(document, index))
            current_id = _transient_annotation_id(current_annotation, safe_annotation_filename, index)
            current_annotation['annotation_id'] = current_id

            if expected_revision is not None and expected_revision != current_revision:
                return {
                    'save': False,
                    'status': 'conflict',
                    'error': 'Annotation file changed since this QA was loaded',
                    'current': current_annotation,
                }
            if expected_annotation_id and current_id and expected_annotation_id != current_id:
                return {
                    'save': False,
                    'status': 'conflict',
                    'error': 'Annotation ID does not match the current file entry',
                    'current': current_annotation,
                }

            save_annotation = deepcopy(updated_data)
            _ensure_annotation_id(save_annotation, expected_annotation_id or current_id)
            if _is_pipeline_v2_document(document):
                annotations[index] = _denormalise_v2_annotation(save_annotation)
            else:
                annotations[index] = save_annotation
            document['annotations'] = annotations
            return {'save': True, 'status': 'ok'}

        mutation = _locked_annotation_mutation(annotation_path, mutate)
        if mutation.get('status') == 'validation_error':
            return _validation_response(mutation.get('error', 'Invalid annotation data'))
        if mutation.get('status') == 'conflict':
            return _conflict_response(mutation.get('error', 'Conflict'), mutation.get('current', {}), mutation['file_revision'])

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation updated and saved to disk: %s index %s in %s", video_filename, index, annotation_path)
        saved_annotation = sanitize_annotation(_normalise_annotation_from_document(mutation['document'], index))
        saved_annotation['annotation_id'] = _transient_annotation_id(saved_annotation, safe_annotation_filename, index)
        return jsonify({
            'success': True,
            'annotation': saved_annotation,
            'annotation_id': saved_annotation.get('annotation_id'),
            'file_revision': mutation['file_revision'],
        })
    except ValueError as exc:
        logger.error("Validation error on update: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except AnnotationLockUnavailable as exc:
        logger.error("Unsafe update refused: %s", exc)
        return jsonify({'success': False, 'code': 'lock_unavailable', 'error': str(exc)}), 503
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

        payload = request.get_json(silent=True) or {}
        expected_annotation_id = _as_dict(payload.get('_source')).get('annotation_id') or payload.get('annotation_id') or ''

        def mutate(document: dict, current_revision: int) -> dict:
            annotations = document.get('annotations', [])
            if index < 0 or index >= len(annotations):
                return {'save': False, 'status': 'validation_error', 'error': 'Invalid annotation index'}
            current_annotation = sanitize_annotation(_normalise_annotation_from_document(document, index))
            current_id = _transient_annotation_id(current_annotation, safe_annotation_filename, index)
            current_annotation['annotation_id'] = current_id
            if expected_annotation_id and expected_annotation_id != current_id:
                return {
                    'save': False,
                    'status': 'conflict',
                    'error': 'Annotation ID does not match the current file entry',
                    'current': current_annotation,
                }
            deleted = annotations.pop(index)
            document['annotations'] = annotations
            return {'save': True, 'status': 'ok', 'deleted': sanitize_annotation(deleted)}

        mutation = _locked_annotation_mutation(annotation_path, mutate)
        if mutation.get('status') == 'validation_error':
            return _validation_response(mutation.get('error', 'Invalid annotation index'))
        if mutation.get('status') == 'conflict':
            return _conflict_response(mutation.get('error', 'Conflict'), mutation.get('current', {}), mutation['file_revision'])

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation deleted and saved to disk: %s index %s in %s", video_filename, index, annotation_path)
        return jsonify({'success': True, 'deleted': mutation.get('deleted'), 'file_revision': mutation['file_revision']})
    except ValueError as exc:
        logger.error("Validation error on delete: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except AnnotationLockUnavailable as exc:
        logger.error("Unsafe delete refused: %s", exc)
        return jsonify({'success': False, 'code': 'lock_unavailable', 'error': str(exc)}), 503
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

        new_annotation, _expected_revision, expected_annotation_id, _has_source_contract = _extract_update_source(deepcopy(request.get_json() or {}))

        validation_errors = _validate_review_annotation(new_annotation)
        if validation_errors:
            return _validation_response('Invalid annotation data', validation_errors)

        if not validate_annotation(deepcopy(new_annotation)):
            is_v2_input = 'question_details' in new_annotation or 'answer_details' in new_annotation
            if not is_v2_input:
                logger.warning("Invalid annotation data on add: %s", new_annotation)
                return _validation_response('Invalid annotation data. Check required fields and types.')

        def mutate(document: dict, _current_revision: int) -> dict:
            annotations = document.get('annotations', [])
            save_annotation = deepcopy(new_annotation)
            _ensure_annotation_id(save_annotation, expected_annotation_id)
            if _is_pipeline_v2_document(document):
                annotations.append(_denormalise_v2_annotation(save_annotation))
            else:
                annotations.append(save_annotation)
            document['annotations'] = annotations
            return {'save': True, 'status': 'ok', 'index': len(annotations) - 1}

        mutation = _locked_annotation_mutation(annotation_path, mutate)

        # Invalidate cache since annotations were modified
        _invalidate_video_cache()

        logger.info("Annotation added and saved to disk: %s in %s", video_filename, annotation_path)
        saved_index = mutation['index']
        saved_annotation = sanitize_annotation(_normalise_annotation_from_document(mutation['document'], saved_index))
        saved_annotation['annotation_id'] = _transient_annotation_id(saved_annotation, safe_annotation_filename, saved_index)
        return jsonify({
            'success': True,
            'annotation': saved_annotation,
            'annotation_id': saved_annotation.get('annotation_id'),
            'file_revision': mutation['file_revision'],
            'index': saved_index,
        })
    except ValueError as exc:
        logger.error("Validation error on add: %s", exc)
        return jsonify({'error': 'Invalid filename'}), 400
    except AnnotationLockUnavailable as exc:
        logger.error("Unsafe add refused: %s", exc)
        return jsonify({'success': False, 'code': 'lock_unavailable', 'error': str(exc)}), 503
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
                'revision': 0,
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
