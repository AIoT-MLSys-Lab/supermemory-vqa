"""
Annotation Data Type System (Python)

This module defines the core data types used in annotations and maps
each annotation entity to its corresponding data type. Each data type
has a specific visualizer and editor component on the frontend.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass


class AnnotationDataType(str, Enum):
    """Enum of all annotation data types"""
    TEXT = "TEXT"
    TIMESPAN = "TIMESPAN"
    TIMESTAMP = "TIMESTAMP"
    BOUNDING_BOX = "BOUNDING_BOX"
    SKILL_TYPE = "SKILL_TYPE"
    MODALITY_LIST = "MODALITY_LIST"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    EVIDENCE_LIST = "EVIDENCE_LIST"
    ANSWER_CHOICES = "ANSWER_CHOICES"


@dataclass
class EditModeConfig:
    """Configuration for edit modes per data type"""
    can_drag_on_canvas: bool = False
    can_drag_on_progress_bar: bool = False
    can_edit_in_panel: bool = True
    requires_direct_input: bool = True


# Edit mode configuration for each data type
EDIT_MODE_CONFIG: Dict[AnnotationDataType, EditModeConfig] = {
    AnnotationDataType.TEXT: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,
        requires_direct_input=True,
    ),
    AnnotationDataType.TIMESPAN: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=True,  # Drag bars on timeline
        can_edit_in_panel=True,
        requires_direct_input=False,
    ),
    AnnotationDataType.TIMESTAMP: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=True,  # Drag marker on timeline
        can_edit_in_panel=True,
        requires_direct_input=False,
    ),
    AnnotationDataType.BOUNDING_BOX: EditModeConfig(
        can_drag_on_canvas=True,  # Drag and resize on video
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,  # Can also edit coordinates manually
        requires_direct_input=False,
    ),
    AnnotationDataType.SKILL_TYPE: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,
        requires_direct_input=True,  # Dropdown only
    ),
    AnnotationDataType.MODALITY_LIST: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,
        requires_direct_input=True,  # Checkboxes only
    ),
    AnnotationDataType.HUMAN_REVIEW: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,
        requires_direct_input=True,  # Dropdown and text input
    ),
    AnnotationDataType.EVIDENCE_LIST: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=True,  # Each timespan can be dragged
        can_edit_in_panel=True,
        requires_direct_input=False,
    ),
    AnnotationDataType.ANSWER_CHOICES: EditModeConfig(
        can_drag_on_canvas=False,
        can_drag_on_progress_bar=False,
        can_edit_in_panel=True,
        requires_direct_input=True,  # Multiple choice editor
    ),
}


@dataclass
class AnnotationDataValue:
    """Base class for all annotation data type values"""
    type: AnnotationDataType


@dataclass
class TextData(AnnotationDataValue):
    """Text data type (for question, answer, room, etc.)"""
    value: Optional[str] = None
    type: AnnotationDataType = AnnotationDataType.TEXT


@dataclass
class TimeSpanData(AnnotationDataValue):
    """TimeSpan data type (for time ranges)"""
    value: Optional[Dict[str, str]] = None  # {start: str, end: str}
    video_path: Optional[str] = None
    editable: bool = True
    type: AnnotationDataType = AnnotationDataType.TIMESPAN


@dataclass
class TimestampData(AnnotationDataValue):
    """Timestamp data type (for single time points)"""
    value: Optional[str] = None  # MM:SS format
    video_path: Optional[str] = None
    editable: bool = True
    type: AnnotationDataType = AnnotationDataType.TIMESTAMP


@dataclass
class BoundingBoxData(AnnotationDataValue):
    """BoundingBox data type"""
    value: Optional[Dict[str, Any]] = None  # box_2d, timestamp, description, etc.
    editable: bool = True
    type: AnnotationDataType = AnnotationDataType.BOUNDING_BOX


@dataclass
class SkillTypeData(AnnotationDataValue):
    """SkillType data type"""
    value: Optional[str] = None
    type: AnnotationDataType = AnnotationDataType.SKILL_TYPE


@dataclass
class ModalityListData(AnnotationDataValue):
    """ModalityList data type"""
    value: Optional[List[str]] = None
    available_modalities: List[str] = None
    type: AnnotationDataType = AnnotationDataType.MODALITY_LIST

    def __post_init__(self):
        if self.available_modalities is None:
            self.available_modalities = [
                "Gaze", "Audio", "Trajectory", "Depth", "Video", "OCR"
            ]


@dataclass
class HumanReviewData(AnnotationDataValue):
    """HumanReview data type"""
    value: Optional[Dict[str, Any]] = None  # status, comment, reviewer, timestamp
    type: AnnotationDataType = AnnotationDataType.HUMAN_REVIEW


@dataclass
class EvidenceListData(AnnotationDataValue):
    """Evidence list data type (collection of timespans with video paths)"""
    value: Optional[List[Dict[str, Any]]] = None  # [{time_spans: [], video_path: str}]
    type: AnnotationDataType = AnnotationDataType.EVIDENCE_LIST


@dataclass
class AnswerChoicesData(AnnotationDataValue):
    """Answer choices data type (multiple choice answer options)"""
    value: Optional[List[Dict[str, Any]]] = None  # [{text: str, choice_type: str, explanation: str}]
    is_answerable: bool = True
    type: AnnotationDataType = AnnotationDataType.ANSWER_CHOICES


# Type alias for all data types
AnnotationData = Union[
    TextData,
    TimeSpanData,
    TimestampData,
    BoundingBoxData,
    SkillTypeData,
    ModalityListData,
    HumanReviewData,
    EvidenceListData,
    AnswerChoicesData,
]


def get_data_type_for_field(field_name: str) -> AnnotationDataType:
    """
    Get the data type for an annotation field.

    Args:
        field_name: Name of the annotation field

    Returns:
        The corresponding AnnotationDataType
    """
    mapping = {
        "question": AnnotationDataType.TEXT,
        "answer": AnnotationDataType.TEXT,
        "room": AnnotationDataType.TEXT,
        "skill": AnnotationDataType.SKILL_TYPE,
        "question_time_span": AnnotationDataType.TIMESPAN,
        "modalities": AnnotationDataType.MODALITY_LIST,
        "human_review": AnnotationDataType.HUMAN_REVIEW,
        "answer_evidence": AnnotationDataType.EVIDENCE_LIST,
        "time_span": AnnotationDataType.TIMESPAN,
        "answer_video_path": AnnotationDataType.TEXT,
        "location": AnnotationDataType.BOUNDING_BOX,
    }
    return mapping.get(field_name, AnnotationDataType.TEXT)


def get_edit_mode_config(data_type: AnnotationDataType) -> EditModeConfig:
    """
    Get the edit mode configuration for a data type.

    Args:
        data_type: The annotation data type

    Returns:
        The EditModeConfig for the data type
    """
    return EDIT_MODE_CONFIG[data_type]
