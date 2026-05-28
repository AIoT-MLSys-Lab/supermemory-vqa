"""
Validation utilities for annotation data
"""
import html
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def _validate_box_2d(box_2d: List) -> bool:
    """
    Validate box_2d array format
    
    Args:
        box_2d: Box coordinates list to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if len(box_2d) == 0:
        # Empty is valid (no location)
        return True

    if len(box_2d) == 4 and all(
            isinstance(coord, (int, float)) for coord in box_2d):
        # Single box with 4 coordinates [x1, y1, x2, y2]
        return True

    # Check if it's an array of boxes
    for box in box_2d:
        if not isinstance(box, list):
            return False
        if len(box) != 4:
            return False
        if not all(isinstance(coord, (int, float)) for coord in box):
            return False

    return True


def _validate_boxes_with_timestamps(boxes: List[Dict[str, Any]]) -> bool:
    """
    Validate boxes array format with timestamps
    
    Args:
        boxes: List of boxes with box_2d and timestamp fields
        
    Returns:
        True if valid format, False otherwise
    """
    if not isinstance(boxes, list):
        return False

    for box_obj in boxes:
        if not isinstance(box_obj, dict):
            return False

        # Validate box_2d field
        if 'box_2d' not in box_obj:
            return False

        box_2d = box_obj['box_2d']
        if not isinstance(box_2d, list):
            return False

        if len(box_2d) != 4:
            return False

        if not all(isinstance(coord, (int, float)) for coord in box_2d):
            return False

        # Validate timestamp field
        if 'timestamp' not in box_obj:
            return False

        if not validate_timestamp(box_obj['timestamp']):
            return False

        # Validate stream field (optional)
        if 'stream' in box_obj:
            if box_obj['stream'] not in ['question', 'answer']:
                return False

    return True


def validate_annotation(annotation: Dict[str, Any]) -> bool:
    """
    Validate that an annotation follows the required schema
    
    Args:
        annotation: Annotation dictionary to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        'video_filename', 'question', 'answer', 'time_span',
        'location', 'room', 'modalities', 'skill'
    ]

    # Check required fields
    for field in required_fields:
        if field not in annotation:
            return False

    # Validate skill
    valid_skills = [
        'object_location_memory', 'conversational_memory', 'visual_recall',
        'timeline_reconstruction', 'intent_recall', 'in_context_retrieval'
    ]
    if annotation['skill'] not in valid_skills:
        return False

    # Validate modalities (sanitize before validation)
    valid_modalities = ['Gaze', 'Audio', 'Trajectory', 'Depth', 'Video', 'OCR']
    if not isinstance(annotation['modalities'], list):
        return False

    # Check for invalid and duplicate modalities
    original_modalities = annotation['modalities'][:]
    invalid_modalities = [m for m in original_modalities if
                          m not in valid_modalities]

    # Log warning if invalid modalities found
    if invalid_modalities:
        logger.warning(
            f"Invalid modalities found and removed: {invalid_modalities}. "
            f"Valid modalities are: {valid_modalities}"
        )

    # Sanitize modalities: remove any invalid entries that AI might have added
    filtered_modalities = [m for m in original_modalities if
                           m in valid_modalities]

    # Check for duplicates
    unique_modalities = []
    duplicates = []
    for m in filtered_modalities:
        if m not in unique_modalities:
            unique_modalities.append(m)
        else:
            duplicates.append(m)

    # Log warning if duplicates found
    if duplicates:
        logger.warning(f"Duplicate modalities found and removed: {duplicates}")

    annotation['modalities'] = unique_modalities

    # Ensure at least one valid modality remains
    if len(annotation['modalities']) == 0:
        # Default to Video if all were invalid
        logger.warning("All modalities were invalid. Defaulting to ['Video']")
        annotation['modalities'] = ['Video']

    # Sanitize video_filename: if it's 'N/A' or empty, try to infer from context
    if not annotation['video_filename'] or annotation[
        'video_filename'] == 'N/A':
        # Set a default - this will be overridden by the actual filename in
        # the service
        annotation['video_filename'] = 'video.mp4'

    # Validate time_span structure
    if not isinstance(annotation['time_span'], dict):
        return False
    if 'start' not in annotation['time_span'] or 'end' not in annotation[
        'time_span']:
        return False

    # Validate time format (MM:SS)
    if not validate_timestamp(annotation['time_span']['start']):
        return False
    if not validate_timestamp(annotation['time_span']['end']):
        return False

    # Validate location structure if present
    if annotation['location'] is not None:
        if not isinstance(annotation['location'], dict):
            return False

        # Check for new format with 'boxes' field containing timestamps
        if 'boxes' in annotation['location']:
            if not _validate_boxes_with_timestamps(
                    annotation['location']['boxes']):
                return False
        # Check for legacy format with 'box_2d' field
        elif 'box_2d' in annotation['location']:
            if not isinstance(annotation['location']['box_2d'], list):
                return False

            # box_2d can be:
            # - empty [] (no location)
            # - single box [x1, y1, x2, y2]
            # - array of boxes [[x1, y1, x2, y2], [x1, y1, x2, y2], ...]
            if not _validate_box_2d(annotation['location']['box_2d']):
                return False
        else:
            # Location must have either 'boxes' or 'box_2d'
            return False

    # Validate optional human_review field if present
    if 'human_review' in annotation and annotation['human_review'] is not None:
        if not isinstance(annotation['human_review'], dict):
            return False
        # human_review should have 'reviewed' boolean, optional 'status'
        # string, and optional 'comment' string
        if 'reviewed' in annotation['human_review']:
            if not isinstance(annotation['human_review']['reviewed'], bool):
                return False
        if 'status' in annotation['human_review']:
            if annotation['human_review']['status'] not in ['pending',
                                                            'accepted',
                                                            'rejected']:
                return False
        if 'comment' in annotation['human_review']:
            if not isinstance(annotation['human_review']['comment'], str):
                return False

    return True


def _timestamp_parts(timestamp: str):
    """Parse M:SS or H:MM:SS into (hours, minutes, seconds)."""
    if not isinstance(timestamp, str):
        return None
    trimmed = timestamp.strip()
    hour_match = re.match(r'^(\d+):(\d{2}):(\d{2})$', trimmed)
    minute_match = re.match(r'^(\d+):(\d{2})$', trimmed)
    if hour_match:
        hours = int(hour_match.group(1))
        minutes = int(hour_match.group(2))
        seconds = int(hour_match.group(3))
        if minutes > 59:
            return None
    elif minute_match:
        hours = 0
        minutes = int(minute_match.group(1))
        seconds = int(minute_match.group(2))
    else:
        return None

    if hours < 0 or minutes < 0 or seconds < 0 or seconds > 59:
        return None
    return hours, minutes, seconds


def validate_timestamp(timestamp: str) -> bool:
    """
    Validate timestamp format (M:SS or H:MM:SS)
    
    Args:
        timestamp: Timestamp string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    return _timestamp_parts(timestamp) is not None


def parse_timestamp(timestamp: str) -> int:
    """
    Parse timestamp string to total seconds
    
    Args:
        timestamp: Timestamp in M:SS or H:MM:SS format
        
    Returns:
        Total seconds as integer
        
    Raises:
        ValueError: If timestamp format is invalid
    """
    if not validate_timestamp(timestamp):
        raise ValueError(f"Invalid timestamp format: {timestamp}")

    hours, minutes, seconds = _timestamp_parts(timestamp)
    return hours * 3600 + minutes * 60 + seconds


def sanitize_html(text: str) -> str:
    """
    Sanitize text to prevent XSS attacks
    
    Args:
        text: Input text
        
    Returns:
        HTML-escaped text
    """
    return html.escape(text)


def sanitize_annotation(annotation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize annotation data to prevent XSS
    
    Args:
        annotation: Annotation dictionary
        
    Returns:
        Sanitized annotation dictionary
    """
    sanitized = annotation.copy()

    # Sanitize text fields - only if they are actually strings!
    # If they are objects (v2 schema), str() will turn them into Python-style dict strings,
    # which corrupts the JSON on save if not handled.
    if 'question' in sanitized and isinstance(sanitized['question'], str):
        sanitized['question'] = sanitize_html(sanitized['question'])
    if 'answer' in sanitized and isinstance(sanitized['answer'], str):
        sanitized['answer'] = sanitize_html(sanitized['answer'])
    if 'room' in sanitized and isinstance(sanitized['room'], str):
        sanitized['room'] = sanitize_html(sanitized['room'])

    # Sanitize human_review comment if present
    if 'human_review' in sanitized and sanitized['human_review'] is not None:
        if 'comment' in sanitized['human_review'] and isinstance(sanitized['human_review']['comment'], str):
            sanitized['human_review']['comment'] = sanitize_html(
                sanitized['human_review']['comment'])

    # Sanitize v2 text fields if present
    if 'confidence_reasoning' in sanitized and isinstance(sanitized['confidence_reasoning'], str):
        sanitized['confidence_reasoning'] = sanitize_html(
            sanitized['confidence_reasoning'])

    return sanitized
