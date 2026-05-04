import json
import logging
import math
import os
import glob
from collections import defaultdict
from typing import List, Dict, Any, Optional


from .concurrent_inference import ConcurrentInferenceRunner
from .verifier import VerificationAndEnhancementStage
from .integrity_utils import validate_temporal_integrity
from .common_utils import (
    strip_ext,
    to_seconds,
    format_seconds,
    validate_qa_timestamps,
    get_question_video_id,
    build_cross_day_summary,
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google.auth.transport.requests").setLevel(logging.WARNING)


class PipelineStage2:
    def __init__(
            self,
            planner_model: Optional[str] = None,
            verifier_model: Optional[str] = None,
            project_id: Optional[str] = None,
            location: str = "us-central1"
    ):
        from .config import PIPELINE_V2_CONFIG
        self.planner_model = planner_model or PIPELINE_V2_CONFIG["stage2_planner_model"]
        self.verifier_model = verifier_model or PIPELINE_V2_CONFIG["stage2_verifier_model"]

        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
            
        self.inference_manager = ConcurrentInferenceRunner(
            api_key=api_key,
            max_workers=PIPELINE_V2_CONFIG.get("max_concurrent_workers", 4)
        )


    def _get_verifier_stage(self, first_video_start_time: float, max_loops: Optional[int] = None):
        from .verifier import VerificationAndEnhancementStage
        return VerificationAndEnhancementStage(
            verifier_model=self.verifier_model,
            inference_manager=self.inference_manager,
            first_video_start_time=first_video_start_time
        )

    def discover_narrations(self, narration_folder: str, file_pattern: str = "*_caption_narrations*.json") -> List[str]:
        """Recursively discover caption narration JSON files in the folder."""
        if not os.path.exists(narration_folder):
            raise FileNotFoundError(f"Folder not found: {narration_folder}")
            
        pattern = os.path.join(narration_folder, "**", file_pattern)
        discovered_paths = glob.glob(pattern, recursive=True)
        return [os.path.abspath(p) for p in discovered_paths]

    def discover_videos(self, video_folder: str) -> Dict[str, str]:
        """Recursively discover videos and map video_id to absolute path."""
        if not os.path.exists(video_folder):
            raise FileNotFoundError(f"Folder not found: {video_folder}")
            
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv')
        discovered_paths = []
        for ext in video_extensions:
            pattern = os.path.join(video_folder, "**", f"*{ext}")
            discovered_paths.extend(glob.glob(pattern, recursive=True))
            
        video_map = {}
        for p in discovered_paths:
            vid_id = os.path.splitext(os.path.basename(p))[0]
            video_map[vid_id] = os.path.abspath(p)
        return video_map

    def build_superledger(self, narration_paths: List[str], video_map: Dict[str, str]) -> Dict[str, Any]:
        """Merge individual narration JSONs into a full superledger."""
        all_videos = []
        all_chunk_captions = []
        total_duration = 0.0
        from .config import PIPELINE_V2_CONFIG
        from .video_utils import get_video_start_time, get_video_duration
        
        # Default config mimicking old Stage 1 settings
        chunk_duration = PIPELINE_V2_CONFIG["chunk_duration"]
        overlap_duration = PIPELINE_V2_CONFIG["overlap_duration"]
        

        
        def _parse_time(time_val) -> float:
            result = to_seconds(time_val)
            return result if result is not None else 0.0

        # Extract metadata for all files to allow for absolute chronological sorting
        prepared_data = []
        for path in narration_paths:
            base = os.path.basename(path)
            video_id = base.replace('_caption_narrations_vertexai.json', '').replace('_caption_narrations.json', '')
            
            # Use original date parsing for fallback/metadata
            parsed_date = "Unknown Date"
            parts = video_id.split('_')
            for i, p in enumerate(parts):
                if len(p) == 8 and p.isdigit() and i > 0:
                    mm, dd, yyyy = p[:2], p[2:4], p[4:]
                    parsed_date = f"{yyyy}-{mm}-{dd}"

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Determine true start time for sorting (True North)
            vrs_start, vrs_duration = 0.0, 0.0
            actual_video_path = video_map.get(video_id, data.get('video_path', ''))
            if actual_video_path and os.path.exists(actual_video_path):
                try:
                    vrs_start = get_video_start_time(actual_video_path)
                    vrs_duration = get_video_duration(actual_video_path)
                except Exception: pass
            
            start_time = vrs_start if vrs_start else data.get('start_time', 0.0)
            duration = vrs_duration if vrs_duration else data.get('duration', 0.0)

            prepared_data.append({
                'video_id': video_id,
                'path': path,
                'data': data,
                'start_time': start_time,
                'duration': duration,
                'parsed_date': parsed_date,
                'video_path': actual_video_path or f"{video_id}.mp4",
                'is_vertex': '_vertexai' in path
            })

        # Keep only one file per video_id (prefer VertexAI version)
        video_id_to_data = {}
        for item in prepared_data:
            vid = item['video_id']
            if vid not in video_id_to_data or (item['is_vertex'] and not video_id_to_data[vid]['is_vertex']):
                video_id_to_data[vid] = item

        # Sort EVERYTHING by absolute UNIX start time
        sorted_prepared = sorted(video_id_to_data.values(), key=lambda x: x['start_time'])

        for item in sorted_prepared:
            video_id = item['video_id']
            data = item['data']
            start_time = item['start_time']
            duration = item['duration']
            
            all_videos.append({
                'video_id': video_id,
                'video_filename': os.path.basename(item['video_path']),
                'video_path': item['video_path'],
                'duration': duration,
                'start_time': start_time,
                'parsed_date': item['parsed_date']
            })
            total_duration += duration
            
            chunks = data.get('chunks')
            if chunks is None:
                # Handle old schema formats
                chunks = []
                for i, cap in enumerate(data.get('captions', [])):
                    chunks.append({
                        'chunk_index': i,
                        'start_time': _parse_time(cap.get('start', 0)),
                        'end_time': _parse_time(cap.get('end', 0)),
                        'caption': cap
                    })

            for chunk in chunks:
                all_chunk_captions.append({
                    'chunk_index': chunk['chunk_index'],
                    'start_time': _parse_time(chunk['start_time']),
                    'end_time': _parse_time(chunk['end_time']),
                    'video_id': video_id,
                    'caption': chunk['caption']
                })
                
        return {
            'videos': all_videos,
            'total_duration': total_duration,
            'chunk_duration': chunk_duration,
            'overlap_duration': overlap_duration,
            'chunk_captions': all_chunk_captions,
            'model_used': "pipeline_v2_stage2"
        }

    def _format_super_ledger_as_text(self, super_ledger: Dict[str, Any], reference_start_time: Optional[float] = None) -> str:
        """Format the superledger dict into a markdown string matching the original pipeline."""
        _IMPORTANCE_BADGE = {"high": "🔴", "medium": "🟡", "low": "🟢"}

        def parse_time_str(time_str: str) -> float:
            result = to_seconds(time_str)
            return result if result is not None else 0.0

        import datetime
        def format_date_time(unix_time: float) -> str:
            dt = datetime.datetime.fromtimestamp(unix_time)
            return dt.strftime('%Y-%m-%d %H:%M (%A)')
            
        def get_recorded_at(abs_time: float, p_date: str) -> str:
            if not abs_time: return "Unknown"
            dt = datetime.datetime.fromtimestamp(abs_time)
            if p_date and p_date != "Unknown Date":
                return f"{p_date} {dt.strftime('%H:%M:%S (%A)')}"
            return format_date_time(abs_time)

        def _description_lines(desc: dict) -> list[str]:
            lines = []
            if desc.get("activities"): lines.append(f"- **Activities:** {desc['activities']}")
            if desc.get("objects"): lines.append(f"- **Objects:** {desc['objects']}")
            if desc.get("environment"): lines.append(f"- **Environment:** {desc['environment']}")
            if desc.get("people"):
                people = desc["people"]
                if isinstance(people, list):
                    lines.append("- **People:**")
                    for item in people:
                        person = item.get('person')
                        description = item.get('description', '').strip()
                        if description:
                            if person: lines.append(f"  - {person}: {description}")
                            else: lines.append(f"  - {description}")
                elif isinstance(people, str):
                    lines.append(f"- **People:** {people}")
            if desc.get("audio_transcript"):
                audio_transcript = desc["audio_transcript"]
                if isinstance(audio_transcript, list):
                    lines.append("- **Audio:**")
                    for item in audio_transcript:
                        speaker = item.get('speaker', None)
                        transcript = item.get('transcript', '').strip()
                        if transcript:
                            if speaker: lines.append(f"  - {speaker}: {transcript}")
                            else: lines.append(f"  - {transcript}")
                elif isinstance(audio_transcript, str):
                    lines.append("- **Audio:**")
                    for line in audio_transcript.split('\n'):
                        if line.strip(): lines.append(f"  - {line.strip()}")
            if desc.get("visible_text"): lines.append(f"- **Visible text:** {desc['visible_text']}")
            return lines

        parts = []
        parts.append("# Super Ledger\n")
        
        total_duration = super_ledger.get('total_duration', 0.0)
        model_used = super_ledger.get('model_used', 'pipeline_v2_stage2')
        chunk_dur = super_ledger.get('chunk_duration', 0)
        overlap_dur = super_ledger.get('overlap_duration', 0)
        
        header_items = []
        header_items.append(f"**Model:** {model_used}")
        header_items.append(f"**Total duration:** 0:00 – {format_seconds(total_duration)} ({int(total_duration)}s)")
        if chunk_dur:
            header_items.append(f"**Chunk / Overlap:** {chunk_dur}s / {overlap_dur}s")
        
        parts.append(" · ".join(header_items) + "\n")
        
        parts.append("## Videos\n")
        parts.append("| # | Video ID | Filename | Date | Duration | Starts at |")
        parts.append("|---|----------|----------|------|----------|-----------|")
        
        videos = super_ledger.get('videos', [])
        if reference_start_time is not None:
            first_video_start_time = reference_start_time
        else:
            first_video_start_time = videos[0].get('start_time', 0.0) if videos else 0.0
        
        for idx, vid in enumerate(videos, 1):
            dur = vid.get('duration', 0.0)
            offset = vid.get('start_time', 0.0) - first_video_start_time
            abs_start = vid.get('start_time', 0.0)
            parsed_date = vid.get('parsed_date')
            recorded_at = get_recorded_at(abs_start, parsed_date)
            parts.append(
                f"| {idx} | {vid.get('video_id')} | {vid.get('video_filename')} | {recorded_at} | "
                f"0:00 – {format_seconds(dur)} | {format_seconds(offset)} |"
            )
        parts.append("")
        parts.append("---\n")
        parts.append("## Annotations\n")
        
        # Sort videos by absolute start_time
        sorted_videos = sorted(videos, key=lambda v: v.get('start_time', 0.0))

        for vid in sorted_videos:
            video_id = vid.get('video_id')
            filename = vid.get('video_filename')
            dur = vid.get('duration', 0.0)
            offset = vid.get('start_time', 0.0) - first_video_start_time
            abs_start = vid.get('start_time', 0.0)
            parsed_date = vid.get('parsed_date')
            recorded_at = get_recorded_at(abs_start, parsed_date)
            
            parts.append(f"### 📹 {video_id}\n")
            meta_line = [
                f"**File:** {filename}" if filename else None,
                f"**Date:** {recorded_at}",
                f"**Duration:** {format_seconds(dur)}",
                f"**Starts:** {format_seconds(offset)} after reference"
            ]
            parts.append(" · ".join([m for m in meta_line if m]) + "\n")
            
            vid_chunks = [c for c in super_ledger.get('chunk_captions', []) if c.get('video_id') == video_id]
            vid_chunks.sort(key=lambda x: x.get('start_time', 0.0))
            
            for chunk in vid_chunks:
                cap = chunk.get('caption', {})
                summary = cap.get('overall_summary')
                if summary:
                    parts.append(f"**Summary:** {summary}\n")
                    
                chunk_offset = chunk.get('start_time', 0.0)
                for seg in cap.get('segments', []):
                    ts = seg.get('time_span', {})
                    
                    # Parse local chunk time strings
                    local_start_str = ts.get('start_time', '0:00')
                    local_end_str = ts.get('end_time', '0:00')
                    local_start_sec = parse_time_str(local_start_str)
                    local_end_sec = parse_time_str(local_end_str)
                    
                    # Local relative to video (already contains chunk offset from Stage 1)
                    vid_offset_start_sec = local_start_sec
                    vid_offset_end_sec = local_end_sec
                    
                    # Write video-local string
                    local_start = format_seconds(vid_offset_start_sec)
                    local_end = format_seconds(vid_offset_end_sec)
                    
                    # Absolute Date and Time
                    abs_start_sec = abs_start + vid_offset_start_sec
                    abs_end_sec = abs_start + vid_offset_end_sec
                    datetime_start_str = get_recorded_at(abs_start_sec, parsed_date)
                    datetime_end_str = get_recorded_at(abs_end_sec, parsed_date)
                    
                    importance = seg.get('importance', 'medium')
                    badge = _IMPORTANCE_BADGE.get(importance.lower(), "")
                    
                    confidence = seg.get('confidence', '')
                    res = seg.get('optimal_resolution', '')
                    rate = seg.get('optimal_sampling_rate', '')
                    
                    stats = []
                    if confidence: stats.append(f"Conf: {confidence.title()}")
                    if res: stats.append(f"Res: {res.title()}")
                    if rate: stats.append(f"Rate: {rate.title()}")
                    stat_string = f" ({' | '.join(stats)})" if stats else ""
                    
                    parts.append(f"**{local_start} – {local_end}** ({datetime_start_str} to {datetime_end_str}) {badge} *{importance}*{stat_string}\n")
                    
                    desc = seg.get('description', {})
                    if desc:
                        desc_lines = _description_lines(desc)
                        parts.extend(desc_lines)
                    else:
                        parts.append(f"{seg.get('text', '')}")
                        
                    parts.append("")  # blank line after segment
                    
            parts.append("\n---\n")
            
        return "\n".join(parts)

    def write_superledger_markdown(self, super_ledger: Dict[str, Any], output_path: str):
        """Write a formatted standard superledger as an .md file."""
        text = self._format_super_ledger_as_text(super_ledger)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        logger.info(f"Written superledger markdown to {output_path}")



    def validate_superledger(self, super_ledger: Dict[str, Any]):
        """Validate that the superledger is mathematically consistent before starting QA generation."""
        from .video_utils import timestamp_to_seconds
        
        logger.info("Validating Super Ledger integrity...")
        durations = {v['video_id']: v.get('duration', 0.0) for v in super_ledger.get('videos', [])}
        
        errors = []
        for v_id, dur in durations.items():
            if dur <= 0:
                errors.append(f"Video {v_id} has invalid duration: {dur}s. VRS sidecar might be missing or corrupted.")
        
        for chunk in super_ledger.get('chunk_captions', []):
            v_id = chunk.get('video_id')
            limit = durations.get(v_id, 0.0)
            
            for i, seg in enumerate(chunk.get('caption', {}).get('segments', [])):
                ts = seg.get('time_span', {})
                # Segments in ledger are video-relative (offset included)
                end_sec = timestamp_to_seconds(ts.get('end_time', "0:00"))
                if end_sec > limit + 0.1:
                    errors.append(f"Boundary Violation: {v_id} Chunk {chunk.get('chunk_index')} Segment {i} ends at {end_sec}s (Video Total: {limit}s)")

        if errors:
            logger.error("Super Ledger Validation FAILED:")
            for err in errors[:10]:
                logger.error(f"  - {err}")
            if len(errors) > 10:
                logger.error(f"  ... and {len(errors)-10} more errors.")
            raise ValueError(f"Super Ledger is inconsistent ({len(errors)} errors). Please run reconstruct_ledger.py first.")
        
        logger.info("Super Ledger validation PASSED.")


    def run(
        self, 
        narration_folder: str, 
        video_folder: str, 
        output_folder: Optional[str] = None, 
        target_annotations: Optional[int] = None,
        qa_per_minute: Optional[float] = None,
        qa_file: Optional[str] = None,
        file_pattern: str = "*_caption_narrations*.json",
        global_qa_ratio: float = 0.5,
        stop_at_generation: bool = False,
        stop_at_ledger: bool = False,
        max_loops: Optional[int] = None,
        force_reprocess: Optional[bool] = None
    ) -> None:
        """Run Stage 2: merge narrations to superledger, generate QA, verify and enhance."""
        from .config import PIPELINE_V2_CONFIG
        
        force_reprocess = force_reprocess if force_reprocess is not None else PIPELINE_V2_CONFIG.get("force_reprocess", False)
        
        # Default output to the narration folder so intermediary files always
        # land in a stable, persistent location even without --output.
        output_folder = output_folder or narration_folder
        
        qa_file = qa_file or PIPELINE_V2_CONFIG.get("qa_file")
        
        logger.info(f"Discovering narrations in {narration_folder} (pattern: {file_pattern})...")
        narration_paths = self.discover_narrations(narration_folder, file_pattern=file_pattern)
        if not narration_paths:
            logger.warning(f"No {file_pattern} files found in {narration_folder}")
            return
            
        logger.info(f"Discovered {len(narration_paths)} narration files in {narration_folder}")
        
        logger.info(f"Discovering videos in {video_folder}...")
        video_map = self.discover_videos(video_folder)
        
        # 1. Build Superledger dict and save JSON & MD
        super_ledger = self.build_superledger(narration_paths, video_map)
        
        # Validate Super Ledger before starting QA Generation
        self.validate_superledger(super_ledger)
        
        # Save exact Markdown & exact JSON dict representation for inspection
        sl_dir = output_folder
        sl_md_path = os.path.join(sl_dir, "super_ledger.md")
        sl_json_path = os.path.join(sl_dir, "super_ledger.json")
        sl_text = self._format_super_ledger_as_text(super_ledger)
        with open(sl_md_path, 'w', encoding='utf-8') as f:
            f.write(sl_text)
        with open(sl_json_path, 'w', encoding='utf-8') as f:
            json.dump(super_ledger, f, indent=2)
        logger.info(f"Saved Super Ledger Markdown to {sl_md_path}")
        logger.info(f"Saved Super Ledger JSON to {sl_json_path}")
        
        if stop_at_ledger:
            logger.info("Stopping after Super Ledger creation as requested (--ledger-only).")
            return
        
        word_count = len(sl_text.split())
        logger.info(f"Superledger length ({word_count} words).")
        
        # Calculate target annotations based on duration if not explicitly provided
        if target_annotations is not None:
            target_annot = target_annotations
        else:
            q_per_min = qa_per_minute if qa_per_minute is not None else PIPELINE_V2_CONFIG.get("target_qa_per_minute", 0.5)
            # Duration is in seconds
            total_minutes = super_ledger['total_duration'] / 60.0
            target_annot = max(1, int(total_minutes * q_per_min))
            logger.info(f"Calculated target annotations: {target_annot} (based on {total_minutes:.2f} mins at {q_per_min} QA/min)")
        
        # Step A: Generate QA Pairs (Planner)
        logger.info(f"Generating QA pairs using {self.planner_model}...")
        
        os.makedirs(sl_dir, exist_ok=True)
        # Enable diagnostics early so all batch/concurrent jobs are logged
        diag_dir = os.path.join(sl_dir, ".diagnostics")
        self.inference_manager.save_token_diagnostics(diag_dir)
        raw_qa_path = os.path.join(sl_dir, "raw_qa_pairs.json")
        
        qa_pairs = None
        
        if not qa_pairs and qa_file and os.path.exists(qa_file):
            logger.info(f"Loading QA pairs from provided file: {qa_file}")
            try:
                with open(qa_file, 'r', encoding='utf-8') as f:
                    qa_data = json.load(f)
                    
                # Handle both direct list of dicts or standard pipeline output
                if isinstance(qa_data, list):
                    qa_pairs = qa_data
                elif isinstance(qa_data, dict) and 'qa_pairs' in qa_data:
                    qa_pairs = qa_data['qa_pairs']
                else:
                    logger.warning(f"Unrecognized format in {qa_file}. Regenerating...")
            except Exception as e:
                logger.warning(f"Failed to read provided QA file: {e}. Regenerating...")

        if not qa_pairs and os.path.exists(raw_qa_path) and not force_reprocess:
            logger.info(f"Loading QA pairs from existing raw QA file: {raw_qa_path}")
            try:
                with open(raw_qa_path, 'r', encoding='utf-8') as f:
                    qa_data = json.load(f)
                    
                if isinstance(qa_data, list):
                    qa_pairs = qa_data
                elif isinstance(qa_data, dict) and 'qa_pairs' in qa_data:
                    qa_pairs = qa_data['qa_pairs']
            except Exception as e:
                logger.warning(f"Failed to read raw QA file: {e}. Regenerating...")

        if not qa_pairs:
            qa_pairs = self._orchestrate_qa_generation_two_step(super_ledger, target_annot, global_qa_ratio=global_qa_ratio)

            try:
                with open(raw_qa_path, 'w', encoding='utf-8') as f:
                    json.dump(qa_pairs, f, indent=2)
                logger.info(f"Saved raw QA pairs to {raw_qa_path}")

                # Verify immediate raw output
                validate_temporal_integrity(qa_pairs, super_ledger, label="Raw QA Generation")

            except Exception as e:
                logger.error(f"Failed to save raw QA pairs: {e}")

        if stop_at_generation:
            logger.info("Stopping after QA generation as requested (--generate-only).")
            return

        if not qa_pairs:
            logger.warning("No QA pairs generated/retrieved.")
            return

        # Step B: Verification & Enhancement
        logger.info(f"Running verifier and enhancer using {self.verifier_model}...")
        video_ids = [strip_ext(v['video_id']) for v in super_ledger['videos']]
        video_paths_map = {strip_ext(v['video_id']): v['video_path'] for v in super_ledger['videos']}
        videos = super_ledger.get('videos', [])
        first_video_start_time = videos[0].get('start_time', 0.0) if videos else 0.0
        
        stage = self._get_verifier_stage(first_video_start_time, max_loops=max_loops)
        
        ledger_text = self._format_super_ledger_as_text(super_ledger)
        final_results = stage.process(
            qa_pairs=qa_pairs,
            super_ledger_dict=super_ledger,
            super_ledger_text=ledger_text,
            video_paths_map=video_paths_map,
            all_video_ids=video_ids,
            output_folder=sl_dir,
            force_reprocess=force_reprocess,
            target_annotations=target_annot,
            qa_generator_func=lambda target: self._orchestrate_qa_generation_two_step(super_ledger, target, global_qa_ratio=global_qa_ratio)
        )
        
        verified_pairs = final_results.get('verified_pairs', [])
        rejected_pairs = final_results.get('rejected_pairs', [])
        
        # Log videos missing QA before distributing
        all_qa = verified_pairs + rejected_pairs
        qa_vids = set()
        for p in all_qa:
            qa_pair = p.get('qa_pair', p)
            vid = qa_pair.get('metadata', {}).get('primary_video_id') or qa_pair.get('question', {}).get('video_id')
            if vid:
                qa_vids.add(vid)
                
        for vid in video_ids:
            if vid not in qa_vids:
                logger.warning(f"Video {vid} has NO generated QA pairs. It might have been skipped during batch generation.")
        
        # Distribute into per-video outputs
        verified_by_video = {}
        rejected_by_video = {}
        
        # Cast timestamps back to video-relative time before saving
        video_offsets = {
            v.get('video_id'): v.get('start_time', 0.0) - first_video_start_time
            for v in videos if v.get('video_id') is not None
        }
        video_durations = {
            v.get('video_id'): v.get('duration', 0.0)
            for v in videos if v.get('video_id') is not None
        }

        def _cast_qa_time(qa):
            return validate_qa_timestamps(qa, video_durations)

        valid_verified = []
        for pair in verified_pairs:
            if _cast_qa_time(pair):
                valid_verified.append(pair)
                vid = get_question_video_id(pair, video_offsets)
                if 'metadata' not in pair: pair['metadata'] = {}
                pair['metadata']['primary_video_id'] = vid
                
                if vid not in verified_by_video: verified_by_video[vid] = []
                verified_by_video[vid].append(pair)
            else:
                rejected_pairs.append({'qa_pair': pair, 'rejection_reason': 'Out of bounds timestamp after casting'})
                
        verified_pairs = valid_verified
        
        valid_rejected = []
        for pair in rejected_pairs:
            qa_pair = pair.get('qa_pair', pair)
            if _cast_qa_time(qa_pair):
                valid_rejected.append(pair)
                vid = get_question_video_id(qa_pair, video_offsets)
                if 'metadata' not in qa_pair: qa_pair['metadata'] = {}
                qa_pair['metadata']['primary_video_id'] = vid

                if vid not in rejected_by_video: rejected_by_video[vid] = []
                rejected_by_video[vid].append(pair)
                
        rejected_pairs = valid_rejected

        # Output saving
        for video_info in super_ledger['videos']:
            vid = video_info['video_id']
            video_path = video_info['video_path']
            
            out_dir = output_folder
            os.makedirs(out_dir, exist_ok=True)
            
            # Write verified pairs
            if vid in verified_by_video:
                vp = os.path.join(out_dir, f"{vid}_verified_annotations.json")
                with open(vp, 'w', encoding='utf-8') as f:
                    json.dump({
                        'video_id': vid,
                        'human_review': {'status': 'pending'}, # Mark verified as approved contextually or strictly pending depending on preference
                        'annotations': verified_by_video[vid]
                    }, f, indent=2)
                logger.info(f"Saved {len(verified_by_video[vid])} verified annotations for {vid} to {vp}")
                
            # Write rejected pairs
            if vid in rejected_by_video:
                rp = os.path.join(out_dir, f"{vid}_rejected_annotations.json")
                with open(rp, 'w', encoding='utf-8') as f:
                    json.dump({
                        'video_id': vid,
                        'human_review': {'status': 'rejected'},
                        'annotations': rejected_by_video[vid]
                    }, f, indent=2)
                logger.info(f"Saved {len(rejected_by_video[vid])} rejected annotations for {vid} to {rp}")
                
        # Final Verification of all verified pairs
        logger.info("--- Performing Final Post-Verification Integrity Check ---")
        validate_temporal_integrity(verified_pairs, super_ledger, label="Final Verified Output")

    @staticmethod
    def _build_cross_day_summary(qa_pairs: List[Dict[str, Any]]) -> str:
        """Build a compact summary of QAs from other days for skill balance guidance."""
        return build_cross_day_summary(qa_pairs)

    def _orchestrate_qa_generation_two_step(self, super_ledger: Dict[str, Any], target_annotations: int, global_qa_ratio: float = 0.5) -> List[Dict[str, Any]]:
        videos = super_ledger.get('videos', [])
        num_days = len({v.get('parsed_date', 'Unknown Date') for v in videos})
        
        if num_days <= 1:
            logger.info(f"Only {num_days} day(s) detected. Forcing all QA to Global mode.")
            global_qa_ratio = 1.0

        global_target = int(target_annotations * global_qa_ratio)
        daily_target_total = target_annotations - global_target
        
        all_qa_pairs = []
        
        # Step 1: Global Generation
        if global_target > 0:
            logger.info(f"--- Starting Global QA Generation (target: {global_target}) ---")
            global_pairs = self._generate_qa_direct(super_ledger, target_annotations=global_target)
            if global_pairs:
                all_qa_pairs.extend(global_pairs)
        
        # Step 2: Per-Day Generation
        if daily_target_total > 0:
            first_video_start_time = videos[0].get('start_time', 0.0)
            
            # Group by parsed_date
            days = defaultdict(list)
            for v in videos:
                date = v.get('parsed_date', 'Unknown Date')
                days[date].append(v)
                
            # Calculate total duration for ratio-based targets
            total_duration = super_ledger.get('total_duration', 0.0)
            if total_duration <= 0:
                total_duration = 1.0 # fallback to avoid div-0
                
            logger.info(f"--- Starting Per-Day QA Generation (total daily target: {daily_target_total} across {len(days)} days) ---")
            
            for date_str, day_videos in days.items():
                day_duration = sum(v.get('duration', 0.0) for v in day_videos)
                
                # Proportional target (ensure at least 1 if we have any duration)
                day_ratio = day_duration / total_duration
                day_target = max(1, int(daily_target_total * day_ratio))
                
                logger.info(f"Day {date_str}: duration {day_duration:.2f}s, target QA: {day_target}")
                
                day_video_ids = {v['video_id'] for v in day_videos}
                
                # Filter chunk captions
                day_chunks = [c for c in super_ledger.get('chunk_captions', []) if c.get('video_id') in day_video_ids]
                
                mini_ledger_dict = {
                    'videos': day_videos,
                    'total_duration': day_duration,
                    'chunk_duration': super_ledger.get('chunk_duration', 0),
                    'overlap_duration': super_ledger.get('overlap_duration', 0),
                    'chunk_captions': day_chunks,
                    'model_used': super_ledger.get('model_used', 'pipeline_v2_stage2')
                }
                
                # Format using global start time so generated timestamps are compatible properly globally
                mini_ledger_text = self._format_super_ledger_as_text(mini_ledger_dict, reference_start_time=first_video_start_time)
                
                # ── Split QAs: same-day (full detail) vs cross-day (compact) ──
                same_day_qas = []
                cross_day_qas = []
                for qa in all_qa_pairs:
                    # A QA is "same-day" if any of its videos overlap with today
                    qa_vids = set()
                    qa_vids.add(qa.get('question', {}).get('video_id', ''))
                    for ev in qa.get('answer', {}).get('evidence_list', []):
                        qa_vids.add(ev.get('video_id', ''))
                    qa_vids.discard('')
                    
                    if qa_vids & day_video_ids:
                        same_day_qas.append(qa)
                    else:
                        cross_day_qas.append(qa)
                
                # Build compact cross-day summary (skill counts + covered entities)
                cross_day_summary = None
                if cross_day_qas:
                    cross_day_summary = self._build_cross_day_summary(cross_day_qas)
                    logger.info(
                        f"Day {date_str}: {len(same_day_qas)} same-day QAs (full detail), "
                        f"{len(cross_day_qas)} cross-day QAs (compact summary)"
                    )
                
                day_pairs = self._generate_qa_direct(
                    mini_ledger_dict,
                    target_annotations=day_target,
                    ledger_text=mini_ledger_text,
                    previous_qa_pairs=same_day_qas,
                    cross_day_summary=cross_day_summary,
                )
                if day_pairs:
                    all_qa_pairs.extend(day_pairs)
                    
        return all_qa_pairs

    def _generate_qa_direct(self, super_ledger: Dict[str, Any], target_annotations: int, ledger_text: Optional[str] = None, previous_qa_pairs: Optional[List[Dict[str, Any]]] = None, cross_day_summary: Optional[str] = None) -> List[Dict[str, Any]]:
        """Directly call batch manager using our new prompts and schemas."""
        from .prompts.qa_generation import get_stage2_qa_generation_prompt, get_stage2_qa_schema, get_stage2_qa_user_prompt
        from .config import PIPELINE_V2_CONFIG
        from google.genai import types
        
        ledger_text = ledger_text or self._format_super_ledger_as_text(super_ledger)
        video_ids = [v.get('video_id') for v in super_ledger.get('videos', []) if v.get('video_id')]
        system_instruction = get_stage2_qa_generation_prompt(ledger_text=ledger_text, available_video_ids=video_ids)
        
        video_ids = [v.get('video_id') for v in super_ledger.get('videos', []) if v.get('video_id')]
        ResponseSchema = get_stage2_qa_schema(video_ids)
        
        # Calculate batches with safety cap at 1.5x expected turns
        batch_size = PIPELINE_V2_CONFIG.get("qa_batch_size", 5)
        expected_turns = (target_annotations + batch_size - 1) // batch_size
        max_turns = int(math.ceil(expected_turns * 1.5))
        
        logger.info(f"Planning up to {max_turns} turns for QA generation "
                    f"(expected: {expected_turns}, target: {target_annotations}).")
        
        all_qa_pairs = []
        remaining = target_annotations
        for turn_idx in range(max_turns):
            if remaining <= 0:
                logger.info("Target QA annotations met. Stopping generation.")
                break
            
            current_batch = min(batch_size, remaining)
        
            # Rebuild a lightweight context of past QA pairs to prevent deduplication
            accumulated_pairs = (previous_qa_pairs or []) + all_qa_pairs
        
            prev_info = []
            if accumulated_pairs:
                for i, p in enumerate(accumulated_pairs):
                    skill = p.get('metadata', {}).get('skill', 'unknown')
                    q_text_val = p.get('question', {}).get('text', '')
                    
                    ev_parts = []
                    for ev in p.get('answer', {}).get('evidence_list', []):
                        ev_ts = ev.get('time_span', {})
                        ev_vid = ev.get('video_id', '?')
                        ev_parts.append(f"{ev_vid} {ev_ts.get('start_time','?')}")
                    ev_str = " → ".join(ev_parts) if ev_parts else "none"
                    
                    short_text = q_text_val[:60] + "..." if len(q_text_val) > 60 else q_text_val
                    prev_info.append(f"- {skill} | {ev_str} | {short_text}")
                    
            prev_summary = "\n".join(prev_info) if prev_info else None
            
            setup_prompt = get_stage2_qa_user_prompt(
                target_annotations=current_batch,
                batch_number=turn_idx + 1,
                total_batches=max_turns,
                previous_batch_summary=prev_summary,
                cross_day_summary=cross_day_summary,
            )

            request = {
                'agent_name': f'stage2_planner_turn_{turn_idx+1}',
                'model_name': self.planner_model,
                'fallback_model_name': None, # Planner does not use fallback
                'confidence_enabled': False,
                'local_video_paths': [], # Text only
                'prompt': setup_prompt,
                'response_schema': ResponseSchema,
                'target_count': current_batch,
                'system_instruction': system_instruction
            }
            
            try:
                results = self.inference_manager.run_parallel([request])
                if results and results[0]['status'] == 'success':
                    outputs = results[0].get('output', {})
                    # For a single-turn request, 'output' is a dict matching the schema.
                    new_pairs = outputs.get('qa_pairs', []) if isinstance(outputs, dict) else []
                    
                    batch_count = len(new_pairs)
                    if batch_count > 0:
                        # Planner does not generate confidence metadata
                        all_qa_pairs.extend(new_pairs)
                        remaining -= batch_count
                        logger.info(
                            f"Turn {turn_idx + 1}/{max_turns}: "
                            f"+{batch_count} QA pairs (running total: {len(all_qa_pairs)}, remaining: {remaining})"
                        )
                    else:
                        logger.warning(f"Turn {turn_idx + 1} generated 0 valid QA pairs.")
                else:
                    logger.error(f"Generation turn {turn_idx + 1} failed: {results[0].get('error') if results else 'Unknown error'}")
            except Exception as e:
                logger.error(f"Execution error on turn {turn_idx + 1}: {e}")
    
        logger.info(f"Total QA pairs generated: {len(all_qa_pairs)} (target: {target_annotations})")
        if len(all_qa_pairs) < target_annotations:
            logger.warning(
                f"Under-generated: got {len(all_qa_pairs)}/{target_annotations} QA pairs "
                f"after {max_turns} turns."
            )
        
        if len(all_qa_pairs) > target_annotations:
            logger.info(f"Truncating {len(all_qa_pairs)} → {target_annotations}")
        return all_qa_pairs[:target_annotations]

if __name__ == "__main__":
    import typer
    from typing_extensions import Annotated
    app = typer.Typer(add_completion=False)

    @app.command()
    def run_stage2_cli(
        narration_folder: Annotated[str, typer.Argument(help="Folder containing *_caption_narrations.json files")],
        video_folder: Annotated[str, typer.Argument(help="Folder containing original video files")],
        output_folder: Annotated[Optional[str], typer.Option("--output", "-o", help="Folder to save Q/A pairs")] = None,
        planner_model: Annotated[Optional[str], typer.Option("--planner-model", help="Gemini model for QA planner")] = None,
        verifier_model: Annotated[Optional[str], typer.Option("--verifier-model", help="Gemini model for verifier")] = None,
        target_annotations: Annotated[Optional[int], typer.Option("--target", "-t", help="Target annotations")] = None,
        global_qa_ratio: Annotated[float, typer.Option("--global-qa-ratio", "-g", help="Ratio of QAs to generate on global context vs per-day context")] = 0.5,
        qa_file: Annotated[Optional[str], typer.Option("--qa-file", help="Path to an existing QA JSON file to reuse")] = None,
        file_pattern: Annotated[str, typer.Option("--file-pattern", help="Glob pattern for discovering narration files")] = "*_caption_narrations*.json",
        generate_only: Annotated[bool, typer.Option("--generate-only", help="Stop after generating raw QA pairs")] = False,
        ledger_only: Annotated[bool, typer.Option("--ledger-only", "-l", help="Stop after creating Super Ledger")] = False,
    ):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        try:
            stage = PipelineStage2(planner_model=planner_model, verifier_model=verifier_model)
            stage.run(narration_folder=narration_folder, video_folder=video_folder, output_folder=output_folder, target_annotations=target_annotations, qa_file=qa_file, file_pattern=file_pattern, global_qa_ratio=global_qa_ratio, stop_at_generation=generate_only, stop_at_ledger=ledger_only)
        except Exception as e:
            logger.error(f"Stage 2 failed: {e}", exc_info=True)
            raise typer.Exit(code=1)

    app()
