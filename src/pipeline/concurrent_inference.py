import logging
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from google.cloud import storage
from pydantic import BaseModel, Field, create_model
from typing import Literal
import os
import threading

from .token_tracker import TokenTracker

def strip_confidence_from_input(data: Any) -> Any:
    """Recursively removes confidence_score and confidence_reasoning from dictionaries/lists."""
    if isinstance(data, dict):
        return {k: strip_confidence_from_input(v) for k, v in data.items() 
                if k not in ("confidence_score", "confidence_reasoning", "confidence")}
    elif isinstance(data, list):
        return [strip_confidence_from_input(item) for item in data]
    return data

def wrap_schema_with_confidence(original_schema: type[BaseModel]) -> type[BaseModel]:
    """Dynamically wraps a Pydantic schema with confidence fields."""
    if not original_schema:
        return None
    return create_model(
        f"ConfidenceWrapped{original_schema.__name__}",
        output=(original_schema, Field(..., description="The main output of the task")),
        confidence_reasoning=(str, Field(..., description="Brief reasoning for the chosen confidence score")),
        confidence_score=(Literal["Low", "Medium", "High"], Field(..., description="Confidence score for the output. 'High' means the input information was well understood and the output was generated confidently, 'Medium' means slight doubt and more powerful model may comprehend input and generate better output, 'Low' means the input information was not well understood and requires more powerful model to generate better output.")),
        __base__=BaseModel
    )

logger = logging.getLogger(__name__)

def _worker_task(client: genai.Client, request: Dict[str, Any], token_tracker: Optional[TokenTracker], storage_client: Optional[storage.Client] = None, gcs_bucket: Optional[str] = None, upload_semaphore: Optional[threading.BoundedSemaphore] = None) -> Dict[str, Any]:
    """
    Worker task that strictly follows the requested lifecycle:
    1. Upload videos
    2. Wait for processing
    3. Infer
    4. Delete videos immediately
    """
    agent_name = request.get('agent_name', 'unknown_agent')
    original_model_name = request.get('model_name', 'gemini-3-flash-preview')
    from .config import PIPELINE_V2_CONFIG
    fallback_model_name = request.get('fallback_model_name')
    fallback_thresholds = request.get('fallback_thresholds', PIPELINE_V2_CONFIG.get("fallback_confidence_thresholds", ["Low", "Medium"]))
    confidence_enabled = request.get('confidence_enabled', False)
    return_confidence_metadata = request.get('return_confidence_metadata', False)
    
    current_model_name = original_model_name
    
    prompt = request.get('prompt', '')
    if isinstance(prompt, dict):
        # Automatically strip if prompt is passed as a dict
        import json
        prompt = json.dumps(strip_confidence_from_input(prompt))
        
    system_instruction = request.get('system_instruction')
    if confidence_enabled and system_instruction:
        system_instruction += "\n\n### CONFIDENCE SCORING\nYou must provide a `confidence_score` ('Low', 'Medium', or 'High') and `confidence_reasoning`. Provide 'High' if you are certain based on evidence, 'Medium' if evidence is slightly ambiguous, and 'Low' if you are guessing or evidence is contradictory."

    local_video_paths = request.get('local_video_paths', [])
    response_schema = request.get('response_schema')
    if confidence_enabled and response_schema:
        response_schema = wrap_schema_with_confidence(response_schema)
        
    multi_turn_prompts = request.get('multi_turn_prompts', []) # Optional list of prompts for a multi-turn chat

    
    max_retries = request.get('max_retries', 5)
    max_file_retries = request.get('max_file_retries', 3)
    
    result = {"status": "error", "error": "Incomplete execution", "fallback_used": False}
    
    for attempt in range(1, max_retries + 1):
        uploaded_files = []
        
        # 1 & 2. Upload and Wait for Videos (with per-file retries)
        active_gfiles = []
        try:
            for path in local_video_paths:
                file_processed = False
                for file_attempt in range(1, max_file_retries + 1):
                    logger.debug(f"[{agent_name}] Uploading {path} (Attempt {file_attempt}/{max_file_retries})")
                    
                    try:
                        if storage_client and gcs_bucket:
                            # Vertex AI / GCS Mode
                            bucket = storage_client.bucket(gcs_bucket)
                            filename = os.path.basename(path)
                            blob_name = f"vertexai_chunks/{int(time.time()*1000)}_{filename}"
                            blob = bucket.blob(blob_name)
                            blob.upload_from_filename(path)
                            uploaded_files.append(blob)
                            
                            gcs_url = f"gs://{gcs_bucket}/{blob_name}"
                            part = types.Part.from_uri(file_uri=gcs_url, mime_type="video/mp4")
                            active_gfiles.append(part)
                            file_processed = True
                            # GCS uploads are generally considered active immediately
                        else:
                            # Standard Gemini API Mode
                            # 0. Quick duration check to avoid 500 errors on malformed files
                            try:
                                import subprocess
                                probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
                                dur_res = subprocess.check_output(probe_cmd).decode().strip()
                                if float(dur_res) <= 0:
                                    logger.error(f"[{agent_name}] Skipping {path}: Duration is 0.0s (malformed).")
                                    file_processed = True # Mark as "processed" but don't add to active_gfiles
                                    break
                            except Exception as probe_err:
                                logger.debug(f"[{agent_name}] Duration probe failed for {path}: {probe_err}")

                            if upload_semaphore:
                                with upload_semaphore:
                                    gfile = client.files.upload(file=path, config=types.UploadFileConfig(mime_type="video/mp4"))
                            else:
                                gfile = client.files.upload(file=path, config=types.UploadFileConfig(mime_type="video/mp4"))
                            uploaded_files.append(gfile) # Track for final cleanup
                            
                            # Wait for processing (with timeout)
                            logger.debug(f"[{agent_name}] Waiting for {path} ({gfile.name}) to become active...")
                            start_wait = time.time()
                            timeout = 300 # 5 minutes
                            while True:
                                if time.time() - start_wait > timeout:
                                    logger.error(f"[{agent_name}] Timeout waiting for file {path} ({gfile.name}) to become ACTIVE.")
                                    break
                                try:
                                    f_info = client.files.get(name=gfile.name)
                                    if f_info.state.name == "ACTIVE":
                                        active_gfiles.append(gfile)
                                        file_processed = True
                                        break
                                    elif f_info.state.name == "FAILED":
                                        logger.warning(f"[{agent_name}] File {path} ({gfile.name}) failed processing in Gemini API.")
                                        try: client.files.delete(name=gfile.name)
                                        except: pass
                                        break 
                                except Exception as poll_err:
                                    poll_err_str = str(poll_err)
                                    if "500" in poll_err_str or "JSON" in poll_err_str:
                                        logger.warning(f"[{agent_name}] Server error (500) while polling {path}. The file may be malformed or server is busy.")
                                        # If it's a persistent 500 error on a specific file, we might want to skip it
                                        if file_attempt > 3:
                                            logger.error(f"[{agent_name}] Persistent 500 error on {path}. Skipping this file.")
                                            file_processed = True 
                                            break
                                    raise poll_err
                                time.sleep(5)
                    except Exception as e:
                        error_str = str(e)
                        logger.warning(f"[{agent_name}] Exception uploading {path}: {error_str}")
                        # If it's a 500 error, sleep a bit longer as the backend might be overloaded
                        wait_time = 2 ** file_attempt
                        if "500" in error_str:
                            wait_time = max(wait_time, 5)
                        time.sleep(wait_time)
                    
                    if file_processed:
                        break
                
                if not file_processed:
                    raise RuntimeError(f"File {path} failed to process after {max_file_retries} attempts.")
                    
            # If files were requested but none made it through, skip this attempt
            if local_video_paths and not active_gfiles:
                raise RuntimeError(
                    f"All {len(local_video_paths)} file(s) failed to upload or process. "
                    "Cannot proceed without video content."
                )
                    
            # 3. Infer
            contents_from_req = request.get('contents')
            if contents_from_req:
                contents = contents_from_req
                # Append videos to the last user turn if present
                if active_gfiles:
                    if contents[-1].role == 'user':
                        # Ensure we are working with types.Part objects
                        for gfile in active_gfiles:
                            if isinstance(gfile, types.Part): # GCS Part
                                contents[-1].parts.append(gfile)
                            else: # Gemini File
                                contents[-1].parts.append(
                                    types.Part.from_uri(file_uri=gfile.uri, mime_type=gfile.mime_type or "video/mp4")
                                )
                    else:
                        contents.append(types.Content(role='user', parts=active_gfiles))
            else:
                # Legacy single-turn behavior: Order parts for prefix-stable context caching: [Prompt, Videos]
                parts = []
                if prompt:
                    if isinstance(prompt, list):
                        parts.extend(prompt)
                    else:
                        parts.append(prompt)
                parts.extend([
                    g if isinstance(g, types.Part) else types.Part.from_uri(file_uri=g.uri, mime_type=g.mime_type or "video/mp4")
                    for g in active_gfiles
                ])
                contents = parts
            
            config_kwargs = {
                "response_mime_type": "application/json",
                "media_resolution": "MEDIA_RESOLUTION_HIGH",
                "thinking_config": types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=-1
                ),
                "temperature": request.get('temperature', 0.7)
            }
            
            # Only use system_instruction in config if not explicitly provided in contents
            if system_instruction and not contents_from_req:
                config_kwargs["system_instruction"] = system_instruction
            
            # Pass the Pydantic class directly — the SDK handles $ref
            # resolution internally.  Avoid Optional[T] in schemas (produces
            # anyOf/default which the API rejects); use plain str instead.
            if response_schema:
                config_kwargs["response_schema"] = response_schema
                    
            config = types.GenerateContentConfig(**config_kwargs)

            qa_id = request.get('context', {}).get('qa_id', 'unknown')
            logger.info(
                f"[{agent_name}:{qa_id}] Generating — model={current_model_name}, "
                f"files={len(active_gfiles)}, attempt={attempt}/{max_retries}"
            )
            
            import json
            
            if multi_turn_prompts:
                # Multi-turn logic
                chat = client.chats.create(model=current_model_name, config=config)
                
                # Send initial contents (prefix-stable ordering)
                initial_parts = []
                if prompt: initial_parts.append(prompt)
                initial_parts.extend(active_gfiles)
                
                if initial_parts:
                    logger.info(f"[{agent_name}] Initializing chat with {len(initial_parts)} parts...")
                    resp = chat.send_message(initial_parts)
                    if resp.usage_metadata and token_tracker:
                        token_tracker.log_usage(agent_name, resp.usage_metadata.prompt_token_count, resp.usage_metadata.candidates_token_count, getattr(resp.usage_metadata, 'cached_content_token_count', 0))
                
                multi_round_outputs = []
                target_count = request.get('target_count', None)
                total_generated = 0
                for m_prompt in multi_turn_prompts:
                    # Early exit if target met
                    if target_count is not None and total_generated >= target_count:
                        logger.info(f"[{agent_name}] Target {target_count} reached after {len(multi_round_outputs)} turns. Stopping early.")
                        break
                    elif target_count is not None and total_generated <= target_count:
                        logger.info(f"[{agent_name}] Starting turn {len(multi_round_outputs)+1}, QA left: {target_count-total_generated}")
                    logger.info(f"[{agent_name}] Sending multi-turn prompt...")
                    resp = chat.send_message([m_prompt])
                    
                    if resp.usage_metadata and token_tracker:
                        token_tracker.log_usage(agent_name, resp.usage_metadata.prompt_token_count, resp.usage_metadata.candidates_token_count, getattr(resp.usage_metadata, 'cached_content_token_count', 0))
                        
                    if not resp.text:
                        raise ValueError(f"Empty response from model in multi-turn. Generation may have been blocked or failed.")
                    text = resp.text.strip()
                    if text.startswith("```json"): text = text[7:]
                    if text.endswith("```"): text = text[:-3]
                    text = text.strip()
                    try:
                        parsed = json.loads(text)
                        
                        if confidence_enabled and isinstance(parsed, dict) and "output" in parsed:
                            conf_score = parsed.get("confidence_score", "Unknown")
                            conf_reason = parsed.get("confidence_reasoning", "")
                            logger.info(f"[{agent_name}] Generated QA with confidence: {conf_score}")
                            parsed = parsed["output"]
                            
                            if return_confidence_metadata and isinstance(parsed, dict):
                                parsed["confidence_score"] = conf_score
                                parsed["confidence_reasoning"] = conf_reason
                            
                        multi_round_outputs.append(parsed)
                        # Count generated items for early exit
                        if target_count is not None and isinstance(parsed, dict) and 'qa_pairs' in parsed:
                            total_generated += len(parsed['qa_pairs'])
                    except Exception as e:
                        raise ValueError(f"Failed to parse round JSON: {e}. Raw text: {text}")
                        
                result['output'] = multi_round_outputs
                
            else:
                # Single turn logic
                # Single turn contents already prepared above
                response = client.models.generate_content(
                    model=current_model_name,
                    contents=contents,
                    config=config
                )
                
                # Track Tokens
                if response.usage_metadata and token_tracker:
                    in_tok = response.usage_metadata.prompt_token_count
                    out_tok = response.usage_metadata.candidates_token_count
                    cached_tok = getattr(response.usage_metadata, 'cached_content_token_count', 0)
                    token_tracker.log_usage(agent_name, in_tok, out_tok, cached_tok)
                    
                if not response.text:
                    raise ValueError(f"Empty response from model. Generation may have been blocked or failed.")
                text = response.text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.endswith("```"): text = text[:-3]
                text = text.strip()
                
                parsed = json.loads(text)
                
                if confidence_enabled and isinstance(parsed, dict) and "output" in parsed:
                    conf_score = parsed.get("confidence_score", "Unknown")
                    conf_reason = parsed.get("confidence_reasoning", "")
                    
                    is_on_fallback = (fallback_model_name and current_model_name == fallback_model_name)
                    if conf_score in fallback_thresholds and fallback_model_name and not is_on_fallback:
                        logger.warning(f"[{agent_name}] Confidence is {conf_score}. Switching to fallback model.")
                        current_model_name = fallback_model_name
                        cached_content_name = None # Clear cache as it is model-specific
                        raise ValueError(f"Insufficient confidence: {conf_score}")
                    elif is_on_fallback and conf_score in fallback_thresholds:
                        logger.info(f"[{agent_name}] Accepting {conf_score} confidence result from fallback model.")
                        
                    result['confidence'] = {"score": conf_score, "reasoning": conf_reason}
                    parsed = parsed["output"]
                    
                    if return_confidence_metadata and isinstance(parsed, dict):
                        parsed["confidence_score"] = conf_score
                        parsed["confidence_reasoning"] = conf_reason
                    
                result['output'] = parsed
            
            result['status'] = 'success'
            result['error'] = None
            result['fallback_used'] = (current_model_name == fallback_model_name and fallback_model_name is not None)
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"[{agent_name}] Worker failed on attempt {attempt}/{max_retries}: {error_str}")
            
            # On 400 INVALID_ARGUMENT, log schema for diagnosis
            if "400" in error_str or "INVALID_ARGUMENT" in error_str:
                if response_schema:
                    try:
                        import json as _json
                        logger.error(
                            f"[{agent_name}] Schema that caused 400: "
                            f"{_json.dumps(response_schema.model_json_schema(), indent=2)[:2000]}"
                        )
                    except Exception:
                        logger.error(f"[{agent_name}] Could not serialize schema for debugging.")
            
            # Fallback for Server/JSON parsing errors
            if "500" in error_str or "Failed to parse" in error_str or "JSON" in error_str or "Insufficient confidence" in error_str:
                if fallback_model_name and current_model_name != fallback_model_name:
                    logger.warning(f"[{agent_name}] Error or low confidence. Using fallback model for next attempt.")
                    current_model_name = fallback_model_name

            result["status"] = "error"
            result["error"] = error_str
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            result['status'] = 'error'
            result['error'] = error_str
            
        finally:
            # 4. DELETE VIDEOS/BLOBS IMMEDIATELY
            for item in uploaded_files:
                try:
                    if hasattr(item, 'bucket'): # GCS Blob
                        item.delete()
                        logger.debug(f"[{agent_name}] Deleted GCS blob {item.name}")
                    else: # Gemini File
                        client.files.delete(name=item.name)
                        logger.debug(f"[{agent_name}] Deleted Gemini file {item.name}")
                except Exception as e:
                    error_str = str(e)
                    if "403" not in error_str and "404" not in error_str and "PERMISSION_DENIED" not in error_str and "NOT_FOUND" not in error_str:
                        logger.warning(f"[{agent_name}] Failed to delete resource: {e}")
                    
        if result["status"] == "success":
            break

    # Return additional context if provided in request
    if 'context' in request:
        result['context'] = request['context']
        
    return result

class ConcurrentInferenceRunner:
    def __init__(self, api_key: Optional[str] = None, vertex_config: Optional[Dict[str, Any]] = None, max_workers: int = 4):
        self.max_workers = max_workers
        self.token_tracker = TokenTracker()
        self.vertex_config = vertex_config
        self.upload_semaphore = threading.BoundedSemaphore(2)
        
        if vertex_config:
            # Vertex AI Client: SDK treats api_key and project/location as mutually exclusive.
            # We prefer api_key if provided, otherwise fallback to project/location (ADC).
            v_api_key = os.environ.get("GOOGLE_CLOUD_API_KEY")
            if v_api_key:
                self.client = genai.Client(
                    vertexai=True, 
                    api_key=v_api_key
                )
            else:
                self.client = genai.Client(
                    vertexai=True,
                    project=vertex_config.get('project_id'),
                    location=vertex_config.get('location', 'us-central1')
                )
            self.storage_client = storage.Client(project=vertex_config.get('project_id'))
            self.gcs_bucket = vertex_config['gcs_bucket']
        else:
            self.api_key = api_key
            self.client = genai.Client(api_key=api_key)
            self.storage_client = None
            self.gcs_bucket = None

    def run_parallel(self, requests: List[Dict[str, Any]], sort_by_context_key: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        results = []
        total_requests = len(requests)
        logger.info(f"Running {total_requests} inference requests in parallel with up to {self.max_workers} workers...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    _worker_task, 
                    self.client, 
                    req, 
                    self.token_tracker,
                    self.storage_client,
                    self.gcs_bucket,
                    self.upload_semaphore
                ): req 
                for req in requests
            }
            
            completed = 0
            success = 0
            failed = 0
            
            for future in as_completed(futures):
                req = futures[future]
                agent_name = req.get('agent_name', 'unknown')
                
                try:
                    res = future.result()
                    results.append(res)
                    if res.get('status') == 'success':
                        success += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"[{agent_name}] Thread execution failed: {e}")
                    failed += 1
                    
                completed += 1
                left = total_requests - completed
                logger.info(f"[{agent_name.capitalize()}] Progress: {completed}/{total_requests} | Success/Verified: {success} | Failed: {failed} | Left: {left}")
        
        if sort_by_context_key:
            logger.info(f"Sorting {len(results)} results by context key: {sort_by_context_key}")
            results.sort(key=lambda x: x['context'].get(sort_by_context_key, 0))
            
        return results

    def save_token_diagnostics(self, output_dir: str):
        self.token_tracker.plot_and_save(output_dir)
