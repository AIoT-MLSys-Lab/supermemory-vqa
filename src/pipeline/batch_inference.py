import json
import logging
import os
import time
import copy
from typing import List, Dict, Any, Optional, Tuple, Union
from google.cloud import storage
from google import genai
from google.genai import types
from .config import PIPELINE_V2_CONFIG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _inline_json_schema_refs(schema: dict) -> dict:
    """Recursively inlines $ref definitions into the schema."""
    resolved = copy.deepcopy(schema)
    defs = resolved.get("$defs", {})

    def expand(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1])
                if target is None:
                    return node
                merged = copy.deepcopy(target)
                for k, v in node.items():
                    if k != "$ref":
                        merged[k] = expand(v)
                return expand(merged)
            return {k: expand(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [expand(x) for x in node]
        return node

    return expand(resolved)


# ---------------------------------------------------------------------------
# JSONL line builders / parsers  (stateless, pure functions)
# ---------------------------------------------------------------------------

def _serialize_contents(contents_from_req: list, video_map: Dict[str, str], local_video_paths: List[str]) -> list:
    """Convert types.Content objects (or dicts) into JSONL-safe dicts,
    appending video file_data parts to the last user turn."""
    json_contents = []
    for c in contents_from_req:
        role = c.role if hasattr(c, 'role') else c.get('role', 'user')
        parts = []
        c_parts = c.parts if hasattr(c, 'parts') else c.get('parts', [])
        for p in c_parts:
            if hasattr(p, 'text') and p.text:
                parts.append({"text": p.text})
            elif isinstance(p, dict) and 'text' in p:
                parts.append({"text": p['text']})
            elif hasattr(p, 'file_data') and p.file_data:
                parts.append({"file_data": {"mime_type": p.file_data.mime_type, "file_uri": p.file_data.file_uri}})
            elif isinstance(p, dict) and 'file_data' in p:
                parts.append({"file_data": p['file_data']})
        json_contents.append({"role": role, "parts": parts})

    # Append videos to the last USER turn
    if local_video_paths:
        last_user_idx = max(
            (i for i, c in enumerate(json_contents) if c['role'] == 'user'),
            default=-1
        )
        video_parts = [
            {"file_data": {"mime_type": "video/mp4", "file_uri": video_map[path]}}
            for path in local_video_paths if path in video_map
        ]
        if last_user_idx != -1:
            json_contents[last_user_idx]["parts"].extend(video_parts)
        elif video_parts:
            json_contents.append({"role": "user", "parts": video_parts})

    return json_contents


def _build_generation_config(req: Dict[str, Any]) -> dict:
    """Build the generation_config block, including inlined response schema."""
    config = {
        "temperature": req.get('temperature', 0.7),
        "response_mime_type": "application/json"
    }
    schema = req.get('response_schema')
    if schema:
        if hasattr(schema, "model_json_schema"):
            schema_dict = schema.model_json_schema()
        elif isinstance(schema, dict):
            schema_dict = schema
        else:
            schema_dict = None
        if schema_dict:
            config["response_schema"] = _inline_json_schema_refs(schema_dict)
    return config


def _build_jsonl_line(req: Dict[str, Any], index: int, video_map: Dict[str, str]) -> Tuple[str, str, dict]:
    """Build a single JSONL line from a request dict.

    Returns (request_key, jsonl_string, context_entry) where context_entry
    is ``{'index': index, 'context': ...}``.
    """
    contents_from_req = req.get('contents')
    if contents_from_req:
        line_request = {
            "contents": _serialize_contents(
                contents_from_req, video_map, req.get('local_video_paths', [])
            )
        }
    else:
        # Legacy prompt-based path
        parts = []
        prompt = req.get('prompt', '')
        if prompt:
            parts.append({"text": prompt})
        for path in req.get('local_video_paths', []):
            gcs_uri = video_map.get(path)
            if gcs_uri:
                parts.append({"file_data": {"mime_type": "video/mp4", "file_uri": gcs_uri}})
        line_request = {"contents": [{"role": "user", "parts": parts}]}

        sys_inst = req.get('system_instruction')
        if sys_inst:
            line_request["system_instruction"] = {"parts": [{"text": sys_inst}]}

    line_request["generation_config"] = _build_generation_config(req)

    request_key = f"req_{index}"
    jsonl_string = json.dumps({"key": request_key, "request": line_request})
    context_entry = {'index': index, 'context': req.get('context', {})}
    return request_key, jsonl_string, context_entry


# ---------------------------------------------------------------------------
# Output line parsers  (stateless, pure functions)
# ---------------------------------------------------------------------------

def _extract_key(raw_line: dict) -> Optional[str]:
    """Return the request key echoed back by Vertex AI, or None."""
    return raw_line.get('key')


def _extract_error(raw_line: dict) -> Optional[str]:
    """Return the error message from the ``status`` or ``error`` fields, or None if clean."""
    # 1. Check the `status` field (JSON string or dict with a non-zero code).
    raw_status = raw_line.get("status")
    if raw_status:
        status_obj = raw_status
        if isinstance(raw_status, str):
            try:
                status_obj = json.loads(raw_status)
            except json.JSONDecodeError:
                return raw_status  # Unparseable string IS the error message
        if isinstance(status_obj, dict) and status_obj.get("code", 0) != 0:
            return status_obj.get("message", f"Batch error code {status_obj.get('code')}")

    # 2. Check a top-level `error` field.
    raw_error = raw_line.get("error")
    if raw_error:
        if isinstance(raw_error, dict):
            return raw_error.get("message", "Unknown error in batch prediction")
        return str(raw_error)

    return None  # No error detected


def _extract_response(raw_line: dict) -> Tuple[Optional[Any], Optional[str]]:
    """Parse the LLM response from a clean output line.

    Returns (parsed_output, error_string).  On success error_string is None.
    """
    response = raw_line.get("response")
    if not response:
        return None, f"Empty response with no error status. Raw keys: {list(raw_line.keys())}"

    candidates = response.get("candidates", [])
    if not candidates:
        return None, "Empty response with no candidates and no error status"

    try:
        text = (
            candidates[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .replace('\u0000', '')
            .strip()
        )
    except (IndexError, AttributeError) as e:
        return None, f"Failed to extract text from candidates: {e}"

    # Strip optional markdown fencing
    if text.startswith("```json"):
        text = text.split("```json")[1].split("```")[0].strip()
    elif text.startswith("```"):
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        # Non-JSON text is still a valid "success" (caller decides how to use it)
        return text, None


def _categorize_error(message: str) -> str:
    """Return a short category label for an error message."""
    msg_lower = message.lower()
    if "unauthenticated" in msg_lower or "authentication" in msg_lower:
        return "auth"
    if "invalid_argument" in msg_lower or "schema" in msg_lower:
        return "schema"
    if "deadline_exceeded" in msg_lower or "timeout" in msg_lower:
        return "timeout"
    return "other"


def _parse_output_line(raw_line: dict) -> Dict[str, Any]:
    """Parse one JSONL output line into a result dict.

    Returns ``{'status': 'success'|'error', 'output': ..., 'error': ...}``.
    """
    error = _extract_error(raw_line)
    if error:
        return {'status': 'error', 'output': None, 'error': error}

    output, parse_error = _extract_response(raw_line)
    if parse_error:
        return {'status': 'error', 'output': None, 'error': parse_error}

    return {'status': 'success', 'output': output, 'error': None}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class BatchInferenceRunner:
    def __init__(self, project_id: str, gcs_bucket: str, location: str = "us-central1", mode: str = "continuous"):
        self.project_id = project_id
        self.gcs_bucket = gcs_bucket
        self.location = location
        self.mode = mode # "continuous" or "interactive"
        self.diagnostics_dir = None
        self.storage_client = storage.Client(project=project_id)
        self.client = genai.Client(
            vertexai=True, 
            api_key=os.environ.get("GOOGLE_CLOUD_API_KEY"),
            project=project_id,
            location=location,
            http_options=types.HttpOptions(api_version="v1"),
        )
        # Dummy token tracker for interface compatibility
        self.token_tracker = None

    def save_token_diagnostics(self, output_dir: str):
        """Save batch input/output JSONL files to a local directory for review."""
        self.diagnostics_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"BatchInferenceRunner: Diagnostics enabled. Files will be saved to {output_dir}")

    def upload_media(self, local_paths: List[str]) -> Dict[str, str]:
        """Uploads local media files to GCS cache and returns a mapping of local_path -> gcs_uri."""
        if not local_paths:
            return {}
            
        unique_paths = set(local_paths)
        video_map = {}
        bucket = self.storage_client.bucket(self.gcs_bucket)
        
        logger.info(f"Checking GCS cache for {len(unique_paths)} unique media files...")
        for path in unique_paths:
            filename = os.path.basename(path)
            # Use a stable cache path for videos to avoid redundant uploads
            blob_name = f"media_cache/{filename}"
            blob = bucket.blob(blob_name)
            
            if not blob.exists():
                logger.debug(f"Uploading {filename} to GCS cache...")
                blob.upload_from_filename(path)
            else:
                logger.debug(f"Using cached GCS version of {filename}")
            
            video_map[path] = f"gs://{self.gcs_bucket}/{blob_name}"
            
        return video_map

    def run_parallel(self, requests: List[Dict[str, Any]], model_name: Optional[str] = None, job_prefix: str = "batch-job", sort_by_context_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias for run_batch to match ConcurrentInferenceRunner interface."""
        # Use model_name from the first request if not explicitly provided
        if not model_name and requests:
            model_name = requests[0].get('model_name')
        results = self.run_batch(requests, model_name or "gemini-2.0-flash", job_prefix=job_prefix)
        
        if sort_by_context_key:
            logger.info(f"Sorting {len(results)} batch results by context key: {sort_by_context_key}")
            results.sort(key=lambda x: x['context'].get(sort_by_context_key, 0))
            
        return results

    # ------------------------------------------------------------------
    # Core batch workflow
    # ------------------------------------------------------------------

    def run_batch(self, requests: List[Dict[str, Any]], model_name: str, job_prefix: str = "batch-job") -> List[Dict[str, Any]]:
        """Runs a Vertex AI Batch Prediction job for Gemini.

        Workflow:  prepare input → submit → poll → parse output.
        """
        timestamp = int(time.time())
        input_uri = f"gs://{self.gcs_bucket}/batch_inputs/{job_prefix}_{timestamp}.jsonl"
        output_uri_prefix = f"gs://{self.gcs_bucket}/batch_outputs/{job_prefix}_{timestamp}"
        bucket = self.storage_client.bucket(self.gcs_bucket)

        # 0. Upload unique videos to GCS
        all_local_videos = {path for req in requests for path in req.get('local_video_paths', [])}
        video_map = self.upload_media(list(all_local_videos))

        # 1. Build JSONL input lines and tracking map
        jsonl_lines, request_key_to_context = self._prepare_input(requests, video_map)

        # Save local diagnostics copy
        if self.diagnostics_dir:
            local_input = os.path.join(self.diagnostics_dir, f"input_{job_prefix}_{timestamp}.jsonl")
            with open(local_input, "w") as f:
                f.write("\n".join(jsonl_lines))
            logger.info(f"Saved local copy of batch input to {local_input}")

        # 2. Interactive mode gate
        if self.mode == "interactive":
            local_jsonl = f"batch_input_{job_prefix}_{timestamp}.jsonl"
            with open(local_jsonl, "w") as f:
                f.write("\n".join(jsonl_lines))
            print(f"\n{'='*60}")
            print(f"INTERACTIVE BATCH MODE: Input file generated at {os.path.abspath(local_jsonl)}")
            print(f"Contains {len(jsonl_lines)} requests.")
            print(f"{'='*60}")
            val = input("Please review the JSONL file. Press Enter to proceed with submission, or type 'cancel' to abort: ")
            if val.lower() == 'cancel':
                logger.warning("Batch job cancelled by user.")
                return [{"status": "error", "error": "Cancelled by user", "context": req.get('context')} for req in requests]

        # 3. Upload JSONL to GCS & submit job
        blob = bucket.blob(f"batch_inputs/{job_prefix}_{timestamp}.jsonl")
        blob.upload_from_string("\n".join(jsonl_lines))
        logger.info(f"Uploaded batch input to {input_uri}")

        job = self.client.batches.create(
            model=model_name,
            src=input_uri,
            config=types.CreateBatchJobConfig(dest=output_uri_prefix)
        )
        logger.info(f"Batch job created: {job.name}. State: {job.state}. Waiting for completion...")

        # 4. Poll until done
        self._poll_until_done(job)

        # 5. Download & parse results
        raw_results = self._download_results(
            f"batch_outputs/{job_prefix}_{timestamp}",
            job_prefix, timestamp
        )

        return self._parse_output(raw_results, request_key_to_context, requests)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prepare_input(self, requests: List[Dict[str, Any]], video_map: Dict[str, str]) -> Tuple[List[str], Dict[str, dict]]:
        """Build JSONL lines and a request-key-to-context tracking map."""
        jsonl_lines = []
        request_key_to_context = {}

        for i, req in enumerate(requests):
            request_key, jsonl_string, context_entry = _build_jsonl_line(req, i, video_map)
            jsonl_lines.append(jsonl_string)
            request_key_to_context[request_key] = context_entry

        return jsonl_lines, request_key_to_context

    def _poll_until_done(self, job) -> None:
        """Block until the batch job reaches a terminal state."""
        timeout_hours = PIPELINE_V2_CONFIG.get("batch_job_timeout_hours", 6)
        timeout_seconds = timeout_hours * 3600
        start_time = time.time()

        while True:
            job_status = self.client.batches.get(name=job.name)
            if job_status.state in [
                "SUCCEEDED", "FAILED", "CANCELLED",
                "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"
            ]:
                logger.info(f"Batch job finished with state: {job_status.state}")
                return

            if time.time() - start_time > timeout_seconds:
                raise TimeoutError(f"Batch job timed out after {timeout_hours} hours. Job name: {job.name}")

            time.sleep(60)

    def _download_results(self, output_dir: str, job_prefix: str, timestamp: int) -> List[dict]:
        """Download all JSONL output blobs and return parsed lines."""
        blobs = list(self.storage_client.list_blobs(self.gcs_bucket, prefix=output_dir))
        raw_results = []
        for b in blobs:
            if not b.name.endswith('.jsonl'):
                continue
            content = b.download_as_text()
            # Save local copy if diagnostics enabled
            if self.diagnostics_dir:
                local_output = os.path.join(
                    self.diagnostics_dir,
                    f"output_{job_prefix}_{timestamp}_{os.path.basename(b.name)}"
                )
                with open(local_output, "w") as f:
                    f.write(content)
                logger.info(f"Saved local copy of batch output to {local_output}")

            for line in content.strip().split('\n'):
                if line:
                    raw_results.append(json.loads(line))

        return raw_results

    def _parse_output(self, raw_results: List[dict], request_key_to_context: Dict[str, dict], requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Match raw output lines back to original requests and return ordered results."""
        # Build lookup from echoed key → raw output line
        key_to_response = {}
        for raw in raw_results:
            key = _extract_key(raw)
            if key:
                key_to_response[key] = raw
            else:
                logger.warning("Batch output line missing 'key' field. Cannot map accurately.")

        # Walk through every original request and resolve its result
        final_results = [None] * len(requests)
        matched_count = 0
        error_categories: Dict[str, int] = {}

        for request_key, item in request_key_to_context.items():
            original_idx = item['index']
            context = item['context']

            if request_key not in key_to_response:
                final_results[original_idx] = {
                    'status': 'error', 'output': None,
                    'error': 'No response found in batch output for this request',
                    'context': context
                }
                continue

            matched_count += 1
            result = _parse_output_line(key_to_response[request_key])
            result['context'] = context

            if result['status'] == 'error':
                cat = _categorize_error(result['error'])
                error_categories[cat] = error_categories.get(cat, 0) + 1

            final_results[original_idx] = result

        # Structured summary
        success_count = sum(1 for r in final_results if r and r.get('status') == 'success')
        fail_count = len(requests) - success_count
        summary_parts = [f"Matched {matched_count}/{len(requests)}", f"Success: {success_count}", f"Failed: {fail_count}"]
        if error_categories:
            cat_str = ", ".join(f"{k}={v}" for k, v in sorted(error_categories.items()))
            summary_parts.append(f"Error breakdown: [{cat_str}]")
            if fail_count > 0:
                for r in final_results:
                    if r and r.get('status') == 'error' and r.get('error'):
                        logger.error(f"Sample batch error: {str(r['error'])[:300]}")
                        break
        logger.info(f"Batch results: {' | '.join(summary_parts)}")

        # Fill any completely missing slots
        for i in range(len(final_results)):
            if final_results[i] is None:
                final_results[i] = {
                    'status': 'error', 'output': None,
                    'error': 'Gemini Batch API did not return a response for this request (dropped or internal error)',
                    'context': requests[i].get('context', {})
                }

        return final_results
