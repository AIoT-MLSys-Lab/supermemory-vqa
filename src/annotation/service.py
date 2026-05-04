"""
Video Annotation Service using Google AI (Gemini) API
Generates QA annotations for egocentric AR super memory assistant
"""
import os
import json
import time
import logging
import traceback
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from google.cloud import storage
from dotenv import load_dotenv
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.prompts import get_prompt_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# GCS configuration (optional)
GCS_BUCKET = os.getenv('GCS_BUCKET', None)
GCS_RETENTION_HOURS = int(os.getenv('GCS_RETENTION_HOURS', '1'))  # Minimum retention time

# Lazy client initialization
_client = None

def get_client():
    """Get or create Gemini API client"""
    global _client
    if _client is None:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client

# The annotation prompt as specified by the user
ANNOTATION_PROMPT = """You are a QA annotation model for an egocentric AR super memory assistant. You process video from wearable glasses and create question and answer sets based on it for a visual question answering dataset. Eye gaze trajectory is shown as colored circles with the larger red circle being the most recent point.

Goal:
Given the video, generate natural, user-like questions and precise answers for a visual question answering dataset. Each question-answer pair must be grounded in the video. The QA pairs should cover a variety of memory skills.

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
1. Propose up to 6 high-quality question/answer pairs.
2. Use a mix of the allowed skills where possible. Aim for 1 question per skill when the data supports it.
3. For each QA pair:
   - Write a natural question a human user might ask later.
   - Identify:
     * time_span where the question would be asked.
     * time_span containing evidence.
     * location points or bounding boxes that are visually relevant.
     * the minimal set of modalities needed for the question and answer.

Please output a JSON array of objects based on the video content provided.

Output Schema: Each object in the array must adhere strictly to the following structure:
{
  "video_filename": "The name of the video file",
  "question": "A specific question about visual details or actions",
  "answer": "A descriptive answer",
  "time_span": {"start": "MM:SS", "end": "MM:SS"},
  "time_span": {"start": "MM:SS", "end": "MM:SS"},
  "location": {
    "boxes": [
      {
        "box_2d": [y1, x1, y2, x2],
        "timestamp": "MM:SS",
        "stream": "question|answer" // Optional: defaults to question if not specified
      }
    ]
  } or null,
  "answer_video_path": "Optional path to separate answer video file",
  "room": "Generic name or names (if user went to different places) of room/place/building",
  "modalities": ["Gaze", "Video", "Trajectory", "Depth"],
  "skill": "visual_recall|object_location_memory|conversational_memory|timeline_reconstruction|intent_recall|in_context_retrieval"
}

Return ONLY the JSON array, no additional text or formatting."""


class VideoAnnotationService:
    """Service to generate annotations for videos using Google AI (Gemini)"""
    
    def __init__(self, model_name='gemini-2.0-flash-exp'):
        """
        Initialize the annotation service
        
        Args:
            model_name: Gemini model to use (default: gemini-2.0-flash-exp for latest capabilities)
                       Other options: gemini-1.5-pro, gemini-1.5-flash
        """
        self.model_name = model_name
        self.client = None  # Lazy initialization
        self.gcs_client = None
        if GCS_BUCKET:
            try:
                self.gcs_client = storage.Client()
                self.bucket = self.gcs_client.bucket(GCS_BUCKET)
                logger.info(f"GCS bucket configured: {GCS_BUCKET}")
            except Exception as e:
                logger.warning(f"GCS not available: {e}")
    
    def _upload_to_gcs(self, video_path: str) -> str:
        """
        Upload video to GCS with minimum retention time
        
        Args:
            video_path: Local path to video file
            
        Returns:
            GCS URI of uploaded file
        """
        if not self.gcs_client or not GCS_BUCKET:
            raise ValueError("GCS not configured")
        
        filename = os.path.basename(video_path)
        blob_name = f"temp_videos/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
        blob = self.bucket.blob(blob_name)
        
        # Set retention/lifecycle
        blob.metadata = {
            'retention_hours': str(GCS_RETENTION_HOURS),
            'uploaded_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Uploading to GCS: {blob_name}")
        blob.upload_from_filename(video_path)
        
        # Set lifecycle rule for automatic deletion
        blob.custom_time = datetime.utcnow() + timedelta(hours=GCS_RETENTION_HOURS)
        blob.patch()
        
        gcs_uri = f"gs://{GCS_BUCKET}/{blob_name}"
        logger.info(f"Uploaded to GCS with {GCS_RETENTION_HOURS}h retention: {gcs_uri}")
        return gcs_uri
    
    def _cleanup_gcs(self, gcs_uri: str):
        """Delete file from GCS"""
        if not self.gcs_client:
            return
        
        try:
            # Extract blob name from gs:// URI
            blob_name = gcs_uri.replace(f"gs://{GCS_BUCKET}/", "")
            blob = self.bucket.blob(blob_name)
            blob.delete()
            logger.info(f"Deleted from GCS: {blob_name}")
        except Exception as e:
            logger.warning(f"Failed to delete from GCS: {e}")
    
    def _upload_video_to_file_api(self, video_path: str):
        """
        Upload video using Gemini's File API for large file support.
        This avoids memory issues with large videos (>2GB).
        
        Args:
            video_path: Local path to video file
            
        Returns:
            Part object referencing the uploaded file
        """
        # Lazy initialize client
        if self.client is None:
            self.client = get_client()
        
        filename = os.path.basename(video_path)
        file_size = os.path.getsize(video_path)
        logger.info(f"Uploading video to File API: {filename} ({file_size / (1024*1024):.1f} MB)")
        
        # Upload file using the File API
        # The File API handles large files via resumable upload
        uploaded_file = self.client.files.upload(
            file=video_path,
            config=types.UploadFileConfig(
                display_name=filename,
                mime_type="video/mp4"
            )
        )
        
        logger.info(f"File uploaded: {uploaded_file.name}, state: {uploaded_file.state}")
        
        # Wait for file to be processed (ACTIVE state)
        # Video files need processing time before they can be used
        max_wait_time = 300  # 5 minutes max wait
        wait_interval = 5
        total_waited = 0
        
        while uploaded_file.state.name == "PROCESSING" and total_waited < max_wait_time:
            logger.info(f"Waiting for file processing... ({total_waited}s)")
            time.sleep(wait_interval)
            total_waited += wait_interval
            # Refresh file status
            uploaded_file = self.client.files.get(name=uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            raise ValueError(f"File processing failed: {uploaded_file.name}")
        
        if uploaded_file.state.name != "ACTIVE":
            logger.warning(f"File may not be fully processed: {uploaded_file.state.name}")
        
        logger.info(f"File ready: {uploaded_file.name} (URI: {uploaded_file.uri})")
        
        # Store the file name for cleanup later
        self._uploaded_file_name = uploaded_file.name
        
        # Return the uploaded file object directly - it can be used in generate_content
        # The File object is automatically handled by the SDK and doesn't embed the content
        return uploaded_file
    
    def _cleanup_file_api(self):
        """Delete file from Gemini File API storage"""
        if not hasattr(self, '_uploaded_file_name') or not self._uploaded_file_name:
            return
        
        try:
            self.client.files.delete(name=self._uploaded_file_name)
            logger.info(f"Deleted from File API: {self._uploaded_file_name}")
            self._uploaded_file_name = None
        except Exception as e:
            logger.warning(f"Failed to delete from File API: {e}")
    
    def annotate_video(self, video_path: str, prompt_id: str = None, **prompt_params) -> dict:
        """
        Generate annotations for a video using Gemini
        
        Args:
            video_path: Path to the video file
            prompt_id: ID of the prompt to use (default: qa_annotation_v1)
            **prompt_params: Additional parameters to pass to prompt template
            
        Returns:
            Dictionary with 'annotations' list and 'metadata' dict
            
        Raises:
            ValueError: If video processing fails
            FileNotFoundError: If video file doesn't exist
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Lazy initialize client
        if self.client is None:
            self.client = get_client()
        
        # Get prompt manager and load prompt
        prompt_manager = get_prompt_manager()
        if prompt_id:
            prompt_def = prompt_manager.get_prompt(prompt_id)
        else:
            prompt_def = prompt_manager.get_default_prompt()
        
        # Render prompt with parameters
        rendered_prompt = prompt_def.render(**prompt_params)
        
        # Track metadata
        annotation_timestamp = datetime.utcnow().isoformat()
        
        gcs_uri = None
        try:
            # Upload to GCS if configured, otherwise use Gemini File API
            if self.gcs_client and GCS_BUCKET:
                gcs_uri = self._upload_to_gcs(video_path)
                video_input = types.Part.from_uri(file_uri=gcs_uri, mime_type="video/mp4")
            else:
                # Use Gemini File API for large video support
                # This avoids OverflowError for videos larger than 2GB
                video_input = self._upload_video_to_file_api(video_path)
            
            logger.info(f"Generating annotations with {self.model_name} using prompt {prompt_def.id}...")
            
            # Configure thinking mode for models that support it (e.g., Gemini 2.5+)
            # This enables the model to show its reasoning process
            generate_config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    include_thoughts=True,  # Include reasoning in response
                    thinking_budget=-1  # Automatic thinking budget (model determines optimal amount)
                )
            )
            
            # Generate annotations using the rendered prompt with thinking mode enabled
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[video_input, rendered_prompt],
                config=generate_config
            )
            
            # Extract thinking content and raw response from the model
            # According to Gemini API, part.thought is a boolean indicating if the part is thinking
            # The actual thought text is in part.text when part.thought=True
            thinking_parts = []
            non_thinking_parts = []
            raw_response_parts = []
            
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        # Capture all parts for raw response
                        if hasattr(part, 'text') and part.text:
                            raw_response_parts.append(part.text)
                        
                        # Check if this part is a thought (part.thought is a boolean)
                        if hasattr(part, 'thought') and part.thought:
                            if hasattr(part, 'text') and part.text:
                                thinking_parts.append(part.text)
                                logger.info(f"Thinking content captured from thought part: {part.text[:200]}...")
                        elif hasattr(part, 'text') and part.text:
                            non_thinking_parts.append(part.text)
            
            # Combine thinking parts
            thinking_content = '\n\n'.join(thinking_parts) if thinking_parts else None
            
            # For raw_response, use non-thinking parts (the actual model output)
            # If no non-thinking parts found, log a warning and fall back to response.text
            if non_thinking_parts:
                response_text = '\n'.join(non_thinking_parts).strip()
            else:
                logger.warning("No non-thinking parts found in response, falling back to response.text")
                response_text = response.text.strip() if hasattr(response, 'text') else ''
            
            # Store full raw response (all parts including thinking) for debugging
            full_raw_response = '\n\n---\n\n'.join(raw_response_parts) if raw_response_parts else response_text
            
            # Try parsing as-is first
            try:
                annotations = json.loads(response_text)
            except json.JSONDecodeError:
                # If that fails, remove markdown code blocks if present
                cleaned_text = response_text
                if cleaned_text.startswith('```'):
                    lines = cleaned_text.split('\n')
                    # Remove first and last lines (``` markers)
                    if len(lines) >= 2:
                        cleaned_text = '\n'.join(lines[1:-1])
                    else:
                        cleaned_text = ''
                cleaned_text = cleaned_text.lstrip()
                # Remove 'json' keyword if present at the start
                if cleaned_text.startswith('json'):
                    cleaned_text = cleaned_text[4:].lstrip()
                
                annotations = json.loads(cleaned_text)
            
            # Add video filename to each annotation if not present
            video_filename = os.path.basename(video_path)
            for annotation in annotations:
                if 'video_filename' not in annotation:
                    annotation['video_filename'] = video_filename
            
            logger.info(f"Generated {len(annotations)} annotations")
            
            # Return annotations with metadata
            result = {
                'annotations': annotations,
                'metadata': {
                    'model': self.model_name,
                    'prompt_id': prompt_def.id,
                    'prompt_name': prompt_def.name,
                    'timestamp': annotation_timestamp,
                    'video_filename': video_filename,
                    'prompt_parameters': prompt_params
                }
            }
            
            # Add thinking content if available
            if thinking_content:
                result['thinking'] = thinking_content
            
            # Add raw response (the non-thinking output used for annotations)
            result['raw_response'] = response_text
            
            # Add full raw response (all parts including thinking) for debugging
            result['full_raw_response'] = full_raw_response
                
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            logger.error(f"Response text: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
            logger.error(traceback.format_exc())
            raise ValueError(f"Failed to parse annotations as JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error annotating video: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
        finally:
            # Clean up GCS file if used
            if gcs_uri:
                try:
                    self._cleanup_gcs(gcs_uri)
                except Exception as e:
                    logger.warning(f"Failed to cleanup GCS file: {str(e)}")
            # Clean up File API file if used
            try:
                self._cleanup_file_api()
            except Exception as e:
                logger.warning(f"Failed to cleanup File API file: {str(e)}")
    
    def save_annotations(self, result: dict, output_path: str):
        """
        Save annotations with metadata to a JSON file.
        Uses file locking to prevent race conditions when multiple users
        are editing annotations simultaneously.
        
        Args:
            result: Dictionary containing 'annotations' and 'metadata'
            output_path: Path to save the JSON file
            
        Raises:
            TimeoutError: If the file lock cannot be acquired
        """
        # Import here to avoid circular imports
        try:
            from visualization.filelock import write_lock
            with write_lock(output_path):
                with open(output_path, 'w') as f:
                    json.dump(result, f, indent=2)
        except ImportError:
            # Fallback for when running standalone without visualization module
            # Note: No concurrency protection in standalone mode
            logger.warning("File locking not available - running without concurrency protection")
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
        logger.info(f"Annotations saved to {output_path}")
    
    def load_annotations(self, annotation_path: str) -> dict:
        """
        Load annotations from a JSON file.
        Uses file locking to prevent reading partial writes when multiple users
        are accessing the same file.
        
        Args:
            annotation_path: Path to the annotation JSON file
            
        Returns:
            Dictionary with 'annotations' and 'metadata' keys, or legacy list wrapped in dict
        """
        if not os.path.exists(annotation_path):
            return {'annotations': [], 'metadata': {}}
        
        # Import here to avoid circular imports
        try:
            from visualization.filelock import read_lock
            with read_lock(annotation_path):
                with open(annotation_path, 'r') as f:
                    data = json.load(f)
        except ImportError:
            # Fallback for when running standalone without visualization module
            # Note: No concurrency protection in standalone mode
            logger.debug("File locking not available - reading without lock")
            with open(annotation_path, 'r') as f:
                data = json.load(f)
        
        # Handle legacy format (just a list)
        if isinstance(data, list):
            return {
                'annotations': data,
                'metadata': {
                    'model': 'unknown',
                    'prompt_id': 'legacy',
                    'timestamp': 'unknown'
                }
            }
        
        return data
    
    @staticmethod
    def get_available_models() -> dict:
        """
        Get list of available Gemini models using known models
        
        Returns:
            Dictionary with 'models' list and 'source' indicating where models came from
        """
        # Known Gemini models that support generateContent (as of Dec 2025)
        KNOWN_MODELS = [
            # Gemini 3 Series (Latest - Preview)
            {
                'id': 'gemini-3-pro-preview',
                'name': 'Gemini 3 Pro (Preview)',
                'description': 'Most intelligent model with state-of-the-art reasoning, agentic workflows, and complex multimodal tasks. 1M token context.'
            },
            {
                'id': 'gemini-3-flash-preview',
                'name': 'Gemini 3 Flash (Preview)',
                'description': 'Pro-level intelligence at Flash speed and pricing. Balanced model for speed, scale, and frontier intelligence. 1M token context.'
            },
            # Gemini 2.5 Series (Stable)
            {
                'id': 'gemini-2.5-pro',
                'name': 'Gemini 2.5 Pro',
                'description': 'State-of-the-art thinking model for complex reasoning in code, math, STEM, and analyzing large datasets with long context.'
            },
            {
                'id': 'gemini-2.5-flash',
                'name': 'Gemini 2.5 Flash',
                'description': 'Best price-performance model for large scale processing, low-latency, high volume tasks with thinking and agentic capabilities.'
            },
            {
                'id': 'gemini-2.5-flash-lite',
                'name': 'Gemini 2.5 Flash-Lite',
                'description': 'Fastest flash model optimized for cost-efficiency and high throughput.'
            },
            # Gemini 2.0 Series (Previous Generation - Stable)
            {
                'id': 'gemini-2.0-flash',
                'name': 'Gemini 2.0 Flash',
                'description': 'Second generation workhorse model with 1M token context window.'
            },
            {
                'id': 'gemini-2.0-flash-lite',
                'name': 'Gemini 2.0 Flash-Lite',
                'description': 'Second generation small workhorse model with 1M token context window.'
            },
            # Gemini 1.5 Series (Legacy - Still Supported)
            {
                'id': 'gemini-1.5-pro',
                'name': 'Gemini 1.5 Pro',
                'description': 'Advanced model with 2M token context window and multimodal support.'
            },
            {
                'id': 'gemini-1.5-flash',
                'name': 'Gemini 1.5 Flash',
                'description': 'Fast and efficient model with multimodal capabilities.'
            },
            {
                'id': 'gemini-1.5-flash-8b',
                'name': 'Gemini 1.5 Flash-8B',
                'description': 'Lightweight model optimized for speed and efficiency.'
            }
        ]
        
        logger.info(f"Using {len(KNOWN_MODELS)} known Gemini models")
        
        return {
            'models': KNOWN_MODELS,
            'source': 'hardcoded',
            'count': len(KNOWN_MODELS)
        }



if __name__ == "__main__":
    # Test the service
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.annotation.service <video_path>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        sys.exit(1)
    
    service = VideoAnnotationService()
    result = service.annotate_video(video_path)
    
    # Save annotations
    output_path = video_path.rsplit('.', 1)[0] + '_annotations.json'
    service.save_annotations(result, output_path)
    
    annotations = result['annotations']
    metadata = result['metadata']
    
    print(f"\nGenerated {len(annotations)} annotations:")
    print(f"Model: {metadata['model']}")
    print(f"Prompt: {metadata['prompt_name']}")
    print(f"Timestamp: {metadata['timestamp']}")
    print("\nAnnotations:")
    for i, ann in enumerate(annotations, 1):
        print(f"{i}. [{ann['skill']}] {ann['question']}")
