"""
Stage 1 V2: Sequential Captioning with Context Caching

Processes video chunks sequentially across all videos in chronological order.
Previous caption summaries are fed as context to maintain narrative consistency.
Uses Gemini explicit context caching to cache the video + system instruction,
keeping only the text prompt (with previous captions) as uncached input.
"""

import json
import logging
import os
import glob
import time
import datetime
from typing import List, Dict, Any, Optional

from google import genai
from google.genai import types

from .video_utils import split_video_into_chunks, get_video_start_time, get_video_duration, extract_session_number
from .prompts.caption_narration import (
    get_stage1_caption_prompt_with_context,
    get_stage1_caption_schema,
)
from .concurrent_inference import ConcurrentInferenceRunner

logger = logging.getLogger(__name__)

# Default sliding window size for previous caption context
DEFAULT_MAX_CONTEXT_CHUNKS = 30

# TTL for explicit context caches (seconds). Each cache is short-lived since
# we only need it for one generation call per chunk.
CACHE_TTL_SECONDS = 300


class PipelineStage1V2:
    """
    Stage 1 V2: Sequential captioning with explicit context caching.
    
    Key differences from Stage 1 V1:
    - Chunks are processed sequentially (not concurrently)
    - Previous caption summaries are provided as context (sliding window)
    - Context carries across video boundaries within the same session
    - Videos are sorted chronologically using vrs.json absolute timestamps
    - Explicit context caching is used to cache video + system instruction
    """

    def __init__(
            self,
            model_name: Optional[str] = None,
            chunk_duration: Optional[int] = None,
            overlap_duration: Optional[int] = None,
            min_chunk_duration: Optional[int] = None,
            max_chunks_per_video: Optional[int] = None,
            chunk_cache_dir: Optional[str] = None,
            max_context_chunks: Optional[int] = None
    ):
        from .config import PIPELINE_V2_CONFIG

        self.model_name = model_name or PIPELINE_V2_CONFIG["stage1_model"]
        self.fallback_model_name = PIPELINE_V2_CONFIG.get("stage1_fallback_model")
        self.chunk_duration = chunk_duration if chunk_duration is not None else PIPELINE_V2_CONFIG["chunk_duration"]
        self.overlap_duration = overlap_duration if overlap_duration is not None else PIPELINE_V2_CONFIG["overlap_duration"]
        self.min_chunk_duration = min_chunk_duration if min_chunk_duration is not None else PIPELINE_V2_CONFIG["min_chunk_duration"]
        self.max_chunks_per_video = max_chunks_per_video if max_chunks_per_video is not None else PIPELINE_V2_CONFIG["max_chunks_per_video"]
        self.chunk_cache_dir = chunk_cache_dir or PIPELINE_V2_CONFIG.get("chunk_cache_dir")
        self.max_context_chunks = max_context_chunks if max_context_chunks is not None else DEFAULT_MAX_CONTEXT_CHUNKS
        self.session_start_time = None

        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        self.runner = ConcurrentInferenceRunner(api_key=api_key, max_workers=1)
        self.token_tracker = self.runner.token_tracker

        logger.info(f"Stage 1 V2: Sequential inference with context caching (model={self.model_name}, fallback={self.fallback_model_name})")
        logger.info(f"  Max context window: {self.max_context_chunks} chunks")

    def discover_videos(self, input_folder: str) -> List[str]:
        """Recursively discover videos in the folder."""
        if not os.path.exists(input_folder):
            raise FileNotFoundError(f"Folder not found: {input_folder}")

        video_extensions = ('.mp4', '.avi', '.mov', '.mkv')
        discovered_paths = []
        for ext in video_extensions:
            pattern = os.path.join(input_folder, "**", f"*{ext}")
            discovered_paths.extend(glob.glob(pattern, recursive=True))

        return [os.path.abspath(p) for p in discovered_paths]

    def _get_video_absolute_start_time(self, video_path: str) -> float:
        """
        Get the absolute start time for a video from its vrs.json sidecar.
        Falls back to 0.0 if no sidecar is available.
        """
        return get_video_start_time(video_path)

    def _sort_videos_chronologically(self, video_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Sort videos by their absolute start time from vrs.json.
        Returns a list of dicts with video metadata.
        """
        video_metas = []
        # Sort video_paths to ensure deterministic order if fallback to running time is needed
        sorted_paths = sorted(video_paths)
        
        current_running_time = 0.0
        
        for path in sorted_paths:
            abs_start = self._get_video_absolute_start_time(path)
            duration = get_video_duration(path)
            video_id = os.path.splitext(os.path.basename(path))[0]
            
            # Fallback to cumulative running time if vrs.json is missing (returns 0.0)
            if abs_start == 0.0:
                abs_start = current_running_time
                
            video_meta = {
                'path': path,
                'video_id': video_id,
                'absolute_start_time': abs_start,
                'duration': duration,
                'session_number': extract_session_number(path)
            }
            video_metas.append(video_meta)
            
            # Update running time for the next video in case it also lacks vrs.json
            current_running_time = abs_start + duration

        # Sort by session number first, then by absolute start time
        video_metas.sort(key=lambda v: (v['session_number'], v['absolute_start_time']))

        logger.info("Videos sorted by session number:")
        for i, vm in enumerate(video_metas):
            abs_s = vm['absolute_start_time']
            start_dt = datetime.datetime.fromtimestamp(abs_s)
            start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"  [{i}] {vm['video_id']} | start={start_str} | duration={vm['duration']:.1f}s")

        return video_metas

    # _upload_and_wait and _delete_file removed as ConcurrentInferenceRunner handles this.

    def _extract_caption_context(self, caption_output: dict, chunk_info: dict, video_meta: dict) -> dict:
        """
        Extract the context information from a caption output for use in subsequent chunks.
        
        Returns a dict suitable for passing to get_stage1_caption_prompt_with_context().
        """
        # Compute absolute times for this chunk
        abs_video_start = video_meta['absolute_start_time']
        chunk_abs_start = abs_video_start + chunk_info['start_time']
        chunk_abs_end = abs_video_start + chunk_info['end_time']

        # Extract people from segments if available
        people = []
        segments = caption_output.get('segments', [])
        seen_persons = set()
        
        extracted_segments = []
        for seg in segments:
            desc = seg.get('description', {})
            if isinstance(desc, dict):
                for person in desc.get('people', []) or []:
                    person_id = person.get('person', '')
                    if person_id and person_id not in seen_persons:
                        seen_persons.add(person_id)
                        people.append({
                            'person': person_id,
                            'description': person.get('description', '')
                        })
                        
            # Store the simplified segment for context history
            time_span = seg.get('time_span', {})
            ts_start = time_span.get('start_time', '')
            ts_end = time_span.get('end_time', '')
            
            if isinstance(desc, dict):
                activities = desc.get('activities', '')
                environment = desc.get('environment', '')
                combined_desc = activities
                if environment:
                    combined_desc += f" (Env: {environment})"
                    
                extracted_segments.append({
                    'time': f"{ts_start} - {ts_end}",
                    'description': combined_desc,
                    'objects': desc.get('objects', []),
                    'visible_text': desc.get('visible_text', '')
                })

        return {
            'video_id': chunk_info['video_id'],
            'chunk_index': chunk_info['chunk_index'],
            'start_time': chunk_abs_start,
            'end_time': chunk_abs_end,
            'overall_summary': caption_output.get('overall_summary', ''),
            'people': people,
            'segments': extracted_segments,
        }

    def _process_chunk(
            self,
            chunk_info: dict,
            video_meta: dict,
            previous_captions_context: List[dict],
            transcript_chunk: List[dict] = None,
            session_registry: dict = None
    ) -> Optional[dict]:
        """
        Process a single chunk sequentially using ConcurrentInferenceRunner.
        Returns the parsed caption output or None on failure.
        """
        video_id = chunk_info['video_id']
        chunk_idx = chunk_info['chunk_index']
        chunk_path = chunk_info['path']

        logger.info(
            f"Processing chunk {chunk_idx} of {video_id} "
            f"[{chunk_info['start_time']:.0f}s-{chunk_info['end_time']:.0f}s] "
            f"(context: {len(previous_captions_context)} prior chunks)"
        )

        try:
            # Compute absolute times for this chunk
            chunk_abs_start = video_meta['absolute_start_time'] + chunk_info['start_time']
            chunk_abs_end = video_meta['absolute_start_time'] + chunk_info['end_time']

            # 2. Build prompt parts for context caching optimization
            from .prompts.caption_narration import (
                get_stage1_system_instruction, 
                get_stage1_context_history, 
                get_stage1_timing_block
            )
            
            system_instruction = get_stage1_system_instruction()
            history_part = get_stage1_context_history(previous_captions_context, max_context_chunks=self.max_context_chunks, session_registry=session_registry)
            timing_part = get_stage1_timing_block(
                current_start_time=chunk_abs_start,
                current_end_time=chunk_abs_end,
                session_start_time=getattr(self, 'session_start_time', None),
                video_start_offset=chunk_info['start_time'],
                transcript_chunk=transcript_chunk
            )

            # Get response schema
            schema_cls = get_stage1_caption_schema(video_id=video_id)

            request = {
                "agent_name": "stage1_v2_captioner",
                "model_name": self.model_name,
                "fallback_model_name": self.fallback_model_name,
                "confidence_enabled": True,
                "return_confidence_metadata": True,
                "prompt": [history_part, timing_part],
                "system_instruction": system_instruction,
                "local_video_paths": [chunk_path],
                "response_schema": schema_cls,
                "temperature": 0.7
            }
            
            start_str = datetime.datetime.fromtimestamp(chunk_abs_start).strftime('%H:%M:%S')
            logger.info(f"Running generation on chunk {chunk_idx} ({start_str}) via inference runner...")
            results = self.runner.run_parallel([request])
            res = results[0]
            
            if res['status'] != 'success':
                logger.error(f"Error processing chunk {chunk_idx} of {video_id}: {res.get('error')}")
                return None
                
            caption_output = res['output']
            
            # Re-inject confidence into segments since the new central wrapper wraps the WHOLE output,
            # but stage 1 originally expected confidence PER SEGMENT. Wait, the wrapper wraps the
            # output with a global confidence. Stage 1 schema has it per segment!
            # If `confidence_enabled` wraps the whole schema, we get a global confidence.
            # I will ensure global confidence is injected if needed, but the original schema 
            # had it inside VideoSegment. Let's let the runner wrap it globally.
            
            # PROGRAMMATICALLY update segment timestamps relative to the video
            from .video_utils import offset_time_string, timestamp_to_seconds
            offset_seconds = chunk_info.get('start_time', 0)
            chunk_duration = chunk_info.get('end_time', 0.0) - chunk_info.get('start_time', 0.0)
            
            if isinstance(caption_output, dict) and 'segments' in caption_output:
                for segment in caption_output['segments']:
                    if isinstance(segment, dict) and 'time_span' in segment:
                        ts = segment['time_span']
                        
                        # Clamp generated local relative time to chunk duration
                        if 'end_time' in ts:
                            local_end = timestamp_to_seconds(ts['end_time'])
                            if local_end > chunk_duration:
                                ts['end_time'] = offset_time_string("0:00", chunk_duration)
                        if 'start_time' in ts:
                            local_start = timestamp_to_seconds(ts['start_time'])
                            if local_start > chunk_duration:
                                ts['start_time'] = offset_time_string("0:00", chunk_duration)
                                
                        # Apply offset to convert to video relative
                        if offset_seconds > 0:
                            if 'start_time' in ts:
                                ts['start_time'] = offset_time_string(ts['start_time'], offset_seconds)
                            if 'end_time' in ts:
                                ts['end_time'] = offset_time_string(ts['end_time'], offset_seconds)

            return caption_output

        except Exception as e:
            logger.error(f"Error processing chunk {chunk_idx} of {video_id}: {e}", exc_info=True)
            return None

    def run(self, input_folder: str, output_folder: Optional[str] = None) -> None:
        """
        Run Stage 1 V2 on a folder of videos.
        
        Videos are sorted chronologically (via vrs.json start times).
        All chunks across all videos are processed sequentially with
        previous caption context carried across video boundaries.
        """
        video_paths = self.discover_videos(input_folder)
        if not video_paths:
            logger.warning(f"No videos found in {input_folder}")
            return

        logger.info(f"Discovered {len(video_paths)} videos in {input_folder}")

        # Sort videos chronologically
        video_metas = self._sort_videos_chronologically(video_paths)
        if not video_metas:
            return
        
        self.session_start_time = video_metas[0]['absolute_start_time']

        # Determine chunk cache directory
        chunk_dir = self.chunk_cache_dir
        if not chunk_dir:
            chunk_dir = os.path.join(input_folder if output_folder is None else output_folder, ".chunks")
        os.makedirs(chunk_dir, exist_ok=True)

        # Audio Extraction and Transcription
        from .video_utils import extract_and_concatenate_audio, run_whisperx, split_transcript_by_video
        
        global_audio_path = os.path.join(chunk_dir, "global_audio.mp3")
        logger.info("Extracting and concatenating audio for WhisperX...")
        audio_path = extract_and_concatenate_audio(video_metas, global_audio_path)
        
        per_video_transcripts = {}
        if audio_path:
            from .config import PIPELINE_V2_CONFIG
            device = PIPELINE_V2_CONFIG.get("whisper_device", "cuda")
            model_name = PIPELINE_V2_CONFIG.get("whisper_model", "large-v3")
            hf_token = PIPELINE_V2_CONFIG.get("hf_token")
            
            logger.info("Running WhisperX on global audio...")
            global_transcript = run_whisperx(audio_path, model_name, device, hf_token)
            
            logger.info("Splitting transcript by video...")
            per_video_transcripts = split_transcript_by_video(global_transcript, video_metas)
            
            # Save per-video transcripts
            for vid_id, transcript in per_video_transcripts.items():
                out_dir = output_folder if output_folder else os.path.dirname(next(m['path'] for m in video_metas if m['video_id'] == vid_id))
                transcript_path = os.path.join(out_dir, f"{vid_id}_whisper_transcript.json")
                try:
                    with open(transcript_path, 'w', encoding='utf-8') as f:
                        json.dump(transcript, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to save transcript for {vid_id}: {e}")

        # Split all videos into chunks
        video_chunks = {}  # video_id -> list of chunk dicts
        for video_meta in video_metas:
            from .config import PIPELINE_V2_CONFIG
            chunks = split_video_into_chunks(
                video_path=video_meta['path'],
                video_id=video_meta['video_id'],
                chunk_duration=self.chunk_duration,
                overlap_duration=self.overlap_duration,
                min_chunk_duration=self.min_chunk_duration,
                max_chunks_per_video=self.max_chunks_per_video,
                chunk_fps=PIPELINE_V2_CONFIG.get("chunk_fps", 4),
                output_dir=chunk_dir
            )
            video_chunks[video_meta['video_id']] = chunks

        total_chunks = sum(len(c) for c in video_chunks.values())
        logger.info(f"Total chunks to process sequentially: {total_chunks}")

        if total_chunks == 0:
            logger.warning("No chunks generated from videos.")
            return

        # Process all chunks sequentially across videos in chronological order
        # This is the core difference from V1: context carries across video boundaries
        previous_captions_context: List[dict] = []
        video_captions: Dict[str, List[dict]] = {}
        global_chunk_counter = 0
        session_registry = {"people": {}}

        for video_meta in video_metas:
            video_id = video_meta['video_id']
            chunks = video_chunks.get(video_id, [])

            if not chunks:
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing video: {video_id} ({len(chunks)} chunks)")
            logger.info(f"{'='*60}")

            video_captions[video_id] = []

            for chunk_info in sorted(chunks, key=lambda c: c['chunk_index']):
                global_chunk_counter += 1
                logger.info(f"\n--- Global chunk {global_chunk_counter}/{total_chunks} ---")

                # Extract transcript chunk (shifted to chunk-relative time)
                transcript_chunk = []
                chunk_vid = video_id
                chunk_start = chunk_info['start_time']
                if chunk_vid in per_video_transcripts:
                    for line in per_video_transcripts[chunk_vid]:
                        if line['end'] >= chunk_info['start_time'] and line['start'] <= chunk_info['end_time']:
                            transcript_chunk.append({
                                'start': max(0.0, line['start'] - chunk_start),
                                'end': max(0.0, line['end'] - chunk_start),
                                'text': line.get('text', ''),
                                'speaker': line.get('speaker', 'UNKNOWN'),
                            })

                caption_output = self._process_chunk(
                    chunk_info=chunk_info,
                    video_meta=video_meta,
                    previous_captions_context=previous_captions_context,
                    transcript_chunk=transcript_chunk,
                    session_registry=session_registry
                )

                if caption_output is None:
                    logger.error(f"Skipping chunk {chunk_info['chunk_index']} of {video_id} due to error")
                    continue

                # Store caption result
                video_captions[video_id].append({
                    'chunk_index': chunk_info['chunk_index'],
                    'start_time': chunk_info['start_time'],
                    'end_time': chunk_info['end_time'],
                    'caption': caption_output
                })

                # Extract context for subsequent chunks
                context_entry = self._extract_caption_context(
                    caption_output=caption_output,
                    chunk_info=chunk_info,
                    video_meta=video_meta
                )
                previous_captions_context.append(context_entry)

                # Update global session registry (People ONLY, keeping the longest description)
                for p in context_entry.get('people', []):
                    pid = p.get('person')
                    desc = p.get('description')
                    if pid and desc:
                        existing_desc = session_registry['people'].get(pid, "")
                        if len(desc) > len(existing_desc):
                            session_registry['people'][pid] = desc

        # Write outputs
        for video_meta in video_metas:
            video_id = video_meta['video_id']
            if video_id not in video_captions or not video_captions[video_id]:
                continue

            captions = video_captions[video_id]
            captions.sort(key=lambda x: x['chunk_index'])

            out_dir = output_folder if output_folder else os.path.dirname(video_meta['path'])
            os.makedirs(out_dir, exist_ok=True)

            out_path = os.path.join(out_dir, f"{video_id}_caption_narrations.json")

            data = {
                'video_id': video_id,
                'video_path': video_meta['path'],
                'duration': video_meta['duration'],
                'start_time': video_meta['absolute_start_time'],
                'chunks': captions
            }

            with open(out_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved narrations for {video_id} to {out_path}")

        # Save diagnostics
        diag_dir = os.path.join(output_folder if output_folder else input_folder, ".diagnostics")
        self.token_tracker.plot_and_save(diag_dir)
        logger.info(f"Token diagnostics saved to {diag_dir}")


if __name__ == "__main__":
    import typer
    from typing_extensions import Annotated
    app = typer.Typer(add_completion=False)

    @app.command()
    def run_stage1_v2_cli(
        input_folder: Annotated[str, typer.Argument(help="Folder containing input videos")],
        output_folder: Annotated[Optional[str], typer.Option("--output", "-o", help="Folder to save caption narrations")] = None,
        model: Annotated[Optional[str], typer.Option("--model", "-m", help="Gemini model to use")] = None,
        max_context: Annotated[int, typer.Option("--max-context", "-c", help="Max previous chunks in context window")] = DEFAULT_MAX_CONTEXT_CHUNKS,
    ):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        try:
            stage = PipelineStage1V2(model_name=model, max_context_chunks=max_context)
            stage.run(input_folder=input_folder, output_folder=output_folder)
        except Exception as e:
            logger.error(f"Stage 1 V2 failed: {e}", exc_info=True)
            raise typer.Exit(code=1)

    app()
