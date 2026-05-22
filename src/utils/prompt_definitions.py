"""
Prompt definitions using Python dataclasses
Each prompt is defined as a Python class for better type safety and IDE support
"""
import json
from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class PromptParameter:
    """Defines an input parameter for a prompt"""
    name: str
    type: str  # 'integer', 'string', 'float', 'boolean'
    description: str
    default: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'description': self.description,
            'default': self.default
        }


@dataclass
class PromptDefinitionBase:
    """Base class for prompt definitions"""
    id: str
    name: str
    description: str
    version: str

    def get_parameters(self) -> List[PromptParameter]:
        """Return list of input parameters"""
        raise NotImplementedError

    def get_template(self) -> str:
        """Return the prompt template string"""
        raise NotImplementedError

    def get_output_schema(self) -> Dict[str, Any]:
        """Return the expected output schema"""
        raise NotImplementedError

    def render(self, **kwargs) -> str:
        """
        Render the prompt template with given parameters
        
        Args:
            **kwargs: Parameter values to substitute in template
            
        Returns:
            Rendered prompt string
        """
        # Start with default values
        params = {}
        for param in self.get_parameters():
            params[param.name] = kwargs.get(param.name, param.default)

        # Add output schema as JSON string
        params['output_schema'] = json.dumps(self.get_output_schema(), indent=2)

        try:
            return self.get_template().format(**params)
        except KeyError as e:
            raise ValueError(f"Missing required parameter: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'input_parameters': {
                param.name: param.to_dict()
                for param in self.get_parameters()
            }
        }


class QAAnnotationV1(PromptDefinitionBase):
    """Full QA annotation prompt for egocentric AR memory assistant"""

    def __init__(self):
        self.id = 'qa_annotation_v1'
        self.name = 'QA Annotation V1'
        self.description = ('Comprehensive QA annotation prompt covering all '
                            'memory skills')
        self.version = '1.0'

    def get_parameters(self) -> List[PromptParameter]:
        return [
            PromptParameter(
                name='max_annotations',
                type='integer',
                description='Maximum number of annotations to generate',
                default=6
            )
        ]

    def get_template(self) -> str:
        return """You are a QA annotation model for an egocentric AR super 
        memory assistant. You process video from wearable glasses and create 
        question and answer sets based on it for a visual question answering 
        dataset. Eye gaze trajectory is shown as colored circles with the 
        larger red circle being the most recent point.

Goal:
Given the video, generate natural, user-like questions and precise answers 
for a visual question answering dataset. Each question-answer pair must be 
grounded in the video. The QA pairs should cover a variety of memory skills.

Memory skills to cover:
1) object_location_memory:
   Track objects and their states and locations, e.g.:
   - "Where did I leave my phone?"
   - "Did I put the clothes on the hanger in the laundry?"
   - "What items are in my fridge?"
2) conversational_memory:
   Track what was said to or about people (A, B, C, ...), e.g.:
   - "What did I say I would do for A?"
   - "What time did I agree to meet with C tomorrow?"
3) visual_recall:
   Recall text and fine visual details, e.g.:
   - "What was the phone number on the billboard?"
   - "Which way was room 574?"
   - "What was the date on the poster?"
4) timeline_reconstruction:
   Summarize or reconstruct routines and temporal order, e.g.:
   - "Summarize my morning routine yesterday."
   - "When did I get home yesterday?"
5) intent_recall:
   Infer explicit or implicit reminders from what the user said or did, e.g.:
   - "Remind me to check the stove before leaving the house."
   - "Remind me to buy eggs when I am at the grocery store."
6) in_context_retrieval:
   Use the current gaze, location, and recent history, e.g.:
   - "What is this painting I am looking at?"
   - "Compare the price of these glasses with the ones I saw earlier?"

Your task:
1. Propose up to {max_annotations} high-quality question/answer pairs.
2. Use a mix of the allowed skills where possible. Aim for 1 question per 
skill when the data supports it.
3. For each QA pair:
   - Write a natural question a human user might ask later.
   - Identify:
     * time_span where the question would be asked.
     * time_span containing evidence.
     * location points or bounding boxes that are visually relevant (can be 
     multiple boxes if the annotation involves multiple locations).
     * the minimal set of modalities needed for the question and answer (
     e.g., ["Video", "Gaze"], ["Video", "Trajectory"]).Select from: "Gaze", 
     "Audio", "Trajectory", "Depth", "Video", "OCR".

Please output a JSON array of objects based on the video content provided.

Output Schema:
{output_schema}

Return ONLY the JSON array, no additional text or formatting."""

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "video_filename": "The name of the video file",
            "question": "A specific question about visual details or actions",
            "answer": "A descriptive answer",
            "time_span": {"start": "MM:SS", "end": "MM:SS"},
            "location": {"box_2d": [[0, 0, 0, 0]]},
            "room": "Generic name or names of room/place/building",
            "modalities": ["Gaze", "Audio", "Trajectory", "Depth", "Video",
                           "OCR"],
            "skill": "visual_recall|object_location_memory"
                     "|conversational_memory|timeline_reconstruction"
                     "|intent_recall|in_context_retrieval"
        }


class SimpleQAV1(PromptDefinitionBase):
    """Simplified QA annotation prompt for basic use cases"""

    def __init__(self):
        self.id = 'simple_qa_v1'
        self.name = 'Simple QA V1'
        self.description = ('Simplified QA annotation prompt focusing on key '
                            'visual questions')
        self.version = '1.0'

    def get_parameters(self) -> List[PromptParameter]:
        return [
            PromptParameter(
                name='max_annotations',
                type='integer',
                description='Number of annotations to generate',
                default=3
            )
        ]

    def get_template(self) -> str:
        return """You are an AI assistant analyzing video content. Generate {max_annotations} question-answer pairs based on the video.

For each question-answer pair:
- Create a natural question about what happens in the video
- Provide a clear, concise answer
- Identify the time range where the answer can be found
- Specify which memory skill is used

Memory skills: object_location_memory, conversational_memory, visual_recall, 
timeline_reconstruction, intent_recall, in_context_retrieval

Output Schema:
{output_schema}

Return ONLY a JSON array, no additional text."""

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "video_filename": "The name of the video file",
            "question": "A specific question about the video",
            "answer": "A descriptive answer",
            "time_span": {"start": "MM:SS", "end": "MM:SS"},
            "location": {"box_2d": [[0, 0, 0, 0]]},
            "room": "room/place name",
            "modalities": ["Video"],
            "skill": "object_location_memory"
        }


class QAAnnotationWithFrameTimestampsV1(PromptDefinitionBase):
    """QA annotation prompt with frame timestamps for bounding boxes"""

    def __init__(self):
        self.id = 'qa_annotation_frame_timestamps_v1'
        self.name = 'QA Annotation with Frame Timestamps V1'
        self.description = ('QA annotation prompt that includes frame '
                            'timestamps for each bounding box')
        self.version = '1.0'

    def get_parameters(self) -> List[PromptParameter]:
        return [
            PromptParameter(
                name='max_annotations',
                type='integer',
                description='Maximum number of annotations to generate',
                default=6
            )
        ]

    def get_template(self) -> str:
        return """You are a QA annotation model for an egocentric AR super 
        memory assistant. You process video from wearable glasses and create 
        question and answer sets based on it for a visual question answering 
        dataset. Eye gaze trajectory is shown as colored circles with the 
        larger red circle being the most recent point.

Goal:
Given the video, generate natural questions that a human user might ask later 
and provide precise answers. This will be used to create a visual question 
answering dataset. Each question-answer pair must be grounded in the video. 
The QA pairs should cover a variety of memory skills.

Memory skills to cover:
1) object_location_memory:
   Track objects and their states and locations, e.g.:
   - "Where did I leave my phone?"
   - "Did I put the clothes on the hanger in the laundry?"
   - "What items are in my fridge?"
2) conversational_memory:
   Track what was said to or about people (A, B, C, ...), e.g.:
   - "What did I say I would do for A?"
   - "What time did I agree to meet with C tomorrow?"
3) visual_recall:
   Recall text and fine visual details, e.g.:
   - "What was the phone number on the billboard?"
   - "Which way was room 574?"
   - "What was the date on the poster?"
4) timeline_reconstruction:
   Summarize or reconstruct routines and temporal order, e.g.:
   - "Summarize my morning routine yesterday."
   - "When did I get home yesterday?"
5) intent_recall:
   Infer explicit or implicit reminders from what the user said or did, e.g.:
   - "Remind me to check the stove before leaving the house."
   - "Remind me to buy eggs when I am at the grocery store."
   - "Remind user to call John at 3 PM."
   - "Window is open. Remind user to close the window when leaving."
6) in_context_retrieval:
   Use the current gaze, location, and recent history, e.g.:
   - "What is this painting I am looking at?"
   - "Compare the price of these glasses with the ones I saw earlier?"

Your task:
1. Propose at least {max_annotations} high-quality question/answer pairs.
2. Use a mix of the allowed skills where possible. Aim for 1 question per 
skill when the data supports it.
3. For each QA pair:
   - Write a natural question a human user might ask later.
   - Identify:
     * time_span where the question would be asked.
     * time_span containing evidence.
     * location points or bounding boxes that are visually relevant. A SINGLE 
     QUESTION can have MULTIPLE bounding boxes if an object appears in 
     different locations or if multiple objects are relevant. For EACH 
     bounding box, include the specific frame timestamp (in MM:SS format) 
     when that object or area is visible.
     * the minimal set of modalities needed for the question and answer (
     e.g., ["Video", "Gaze"]). Select from: "Gaze", "Audio", "Trajectory", 
     "Depth", "Video", "OCR".

IMPORTANT - Bounding Box Format:
- Each bounding box must use the format: [y1, x1, y2, x2] (row-major order)
- Coordinates are in PIXELS (not normalized)
- (y1, x1) is the top-left corner
- (y2, x2) is the bottom-right corner
- y increases from top to bottom, x increases from left to right
- Example: [50, 100, 150, 200] means a box from pixel row 50, column 100 to 
row 150, column 200
Boxes should be shown at the specific frame timestamp when the object or area 
is visible. Use multiple boxes for different objects or to show change of 
location of object.
Please output a JSON array of objects based on the video content provided.

Output Schema:
{output_schema}

Return ONLY the JSON array, no additional text or formatting."""

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "video_filename": "The name of the video file",
            "question": "A specific question about visual details or actions",
            "answer": "A descriptive answer",
            "time_span": {"start": "MM:SS", "end": "MM:SS"},
            "location": {
                "boxes": [
                    {
                        "box_2d": ["y1", "x1", "y2", "x2"],
                        "timestamp": "MM:SS",
                        "description": "Optional: what this box contains ("
                                       "e.g., 'coffee cup on counter')"
                    }
                ]
            },
            "room": "Generic name or names of room/place/building",
            "modalities": ["Gaze", "Audio", "Trajectory", "Depth", "Video",
                           "OCR"],
            "skill": "visual_recall|object_location_memory"
                     "|conversational_memory|timeline_reconstruction"
                     "|intent_recall|in_context_retrieval"
        }


class QAAnnotationWithQuestionTimespanV1(PromptDefinitionBase):
    """QA annotation prompt with both question and answer timespans"""

    def __init__(self):
        self.id = 'qa_annotation_question_timespan_v1'
        self.name = 'QA Annotation with Question Timespan V1'
        self.description = ('QA annotation prompt that includes timespan for '
                            'when a question might be asked by a human, '
                            'in addition to the answer timespan')
        self.version = '1.0'

    def get_parameters(self) -> List[PromptParameter]:
        return [
            PromptParameter(
                name='max_annotations',
                type='integer',
                description='Maximum number of annotations to generate',
                default=6
            )
        ]

    def get_template(self) -> str:
        return """You are a QA annotation model for an egocentric AR super 
        memory assistant. You process video from wearable glasses and create 
        question and answer sets based on it for a visual question answering 
        dataset. Eye gaze trajectory is shown as colored circles with the 
        larger red circle being the most recent point.

Goal:
Given the video, generate natural questions that a human user might ask later 
and provide precise answers. This will be used to create a visual question 
answering dataset. Each question-answer pair must be grounded in the video. 
The QA pairs should cover a variety of memory skills.

Memory skills to cover:
1) object_location_memory:
   Track objects and their states and locations, e.g.:
   - "Where did I leave my phone?"
   - "Did I put the clothes on the hanger in the laundry?"
   - "What items are in my fridge?"
2) conversational_memory:
   Track what was said to or about people (A, B, C, ...), e.g.:
   - "What did I say I would do for A?"
   - "What time did I agree to meet with C tomorrow?"
3) visual_recall:
   Recall text and fine visual details, e.g.:
   - "What was the phone number on the billboard?"
   - "Which way was room 574?"
   - "What was the date on the poster?"
4) timeline_reconstruction:
   Summarize or reconstruct routines and temporal order, e.g.:
   - "Summarize my morning routine yesterday."
   - "When did I get home yesterday?"
5) intent_recall:
   Infer explicit or implicit reminders from what the user said or did, e.g.:
   - "Remind me to check the stove before leaving the house."
   - "Remind me to buy eggs when I am at the grocery store."
   - "Remind user to call John at 3 PM."
   - "Window is open. Remind user to close the window when leaving."
6) in_context_retrieval:
   Use the current gaze, location, and recent history, e.g.:
   - "What is this painting I am looking at?"
   - "Compare the price of these glasses with the ones I saw earlier?"

Your task:
1. Propose at least {max_annotations} high-quality question/answer pairs.
2. Use a mix of the allowed skills where possible. Aim for 1 question per 
skill when the data supports it.
3. For each QA pair:
   - Write a natural question a human user might ask later.
   - Identify:
     * question_time_span: The time range during or after which a real human 
     might naturally ask this question. This represents the context or 
     trigger moment for the question.
     * time_span: The time range containing evidence needed to answer the 
     question (answer timespan).
     * location points or bounding boxes that are visually relevant. A SINGLE 
     QUESTION can have MULTIPLE bounding boxes if an object appears in 
     different locations or if multiple objects are relevant. For EACH 
     bounding box, include the specific frame timestamp (in MM:SS format) 
     when that object or area is visible.
     * the minimal set of modalities needed for the question and answer (
     e.g., ["Video", "Gaze"], ["Video", "Trajectory"]). Select from: "Gaze", 
     "Audio", "Trajectory", "Depth", "Video", "OCR".

IMPORTANT - Timespan Guidelines:
- question_time_span: When would a user naturally ask this question? For 
example, if a user puts down their keys at 01:30, they might ask "Where are 
my keys?" at 05:00 when they need to leave.
- time_span: Where in the video is the evidence to answer the question? Using 
the same example, the evidence is at 01:30 when the keys were placed.

IMPORTANT - Bounding Box Format:
- Each bounding box must use the format: [y1, x1, y2, x2] (row-major order)
- Coordinates are in PIXELS (not normalized)
- (y1, x1) is the top-left corner
- (y2, x2) is the bottom-right corner
- y increases from top to bottom, x increases from left to right
- Example: [50, 100, 150, 200] means a box from pixel row 50, column 100 to 
row 150, column 200
Boxes should be shown at the specific frame timestamp when the object or area 
is visible. Use multiple boxes for different objects or to show change of 
location of object.
Please output a JSON array of objects based on the video content provided.

Output Schema:
{output_schema}

Return ONLY the JSON array, no additional text or formatting."""

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "video_filename": "The name of the video file",
            "question": "A specific question about visual details or actions",
            "answer": "A descriptive answer",
            "question_time_span": {"start": "MM:SS", "end": "MM:SS"},
            "time_span": {"start": "MM:SS", "end": "MM:SS"},
            "location": {
                "boxes": [
                    {
                        "box_2d": ["y1", "x1", "y2", "x2"],
                        "timestamp": "MM:SS",
                        "description": "Optional: what this box contains ("
                                       "e.g., 'coffee cup on counter')"
                    }
                ]
            },
            "room": "Generic name or names of room/place/building",
            "modalities": ["Gaze", "Audio", "Trajectory", "Depth", "Video",
                           "OCR"],
            "skill": "visual_recall|object_location_memory"
                     "|conversational_memory|timeline_reconstruction"
                     "|intent_recall|in_context_retrieval"
        }


# Registry of all available prompts
PROMPT_REGISTRY: Dict[str, type] = {
    'qa_annotation_v1': QAAnnotationV1,
    'simple_qa_v1': SimpleQAV1,
    'qa_annotation_frame_timestamps_v1': QAAnnotationWithFrameTimestampsV1,
    'qa_annotation_question_timespan_v1': QAAnnotationWithQuestionTimespanV1,
}


def get_all_prompts() -> Dict[str, PromptDefinitionBase]:
    """Get all available prompt instances"""
    return {
        prompt_id: prompt_class()
        for prompt_id, prompt_class in PROMPT_REGISTRY.items()
    }


def get_prompt(prompt_id: str) -> PromptDefinitionBase:
    """Get a specific prompt instance by ID"""
    if prompt_id not in PROMPT_REGISTRY:
        raise KeyError(f"Prompt not found: {prompt_id}")
    return PROMPT_REGISTRY[prompt_id]()
