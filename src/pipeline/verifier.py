import copy
import json
import logging
import os
import tempfile
from typing import List, Dict, Any, Optional, Union
from .concurrent_inference import ConcurrentInferenceRunner
from .batch_inference import BatchInferenceRunner
from .prompts.verification import get_verifier_system_prompt, get_verifier_user_prompt, get_stage2_verifier_schema
from .prompts.enhancement import get_enhancer_system_prompt, get_enhancer_user_prompt, get_stage2_enhancer_schema
from .prompts.video_chunk_retrieval import get_video_chunk_retrieval_system_prompt, get_video_chunk_retrieval_user_prompt, get_stage2_retrieval_schema
from .config import PIPELINE_V2_CONFIG

from .common_utils import (
    strip_ext,
    get_span_bounds,
    to_seconds,
    format_abs_time,
    absolute_seconds,
    filter_causal_answer_evidence,
    get_or_extract_clip,
    extract_clip,
)

# Backward-compatible aliases for callers that import private names
_get_span_bounds = get_span_bounds
_to_seconds = to_seconds
_format_abs_time = format_abs_time
_absolute_seconds = absolute_seconds
_filter_causal_answer_evidence = filter_causal_answer_evidence

class VerificationAndEnhancementStage:
    def __init__(self, verifier_model: str, inference_manager: Union[ConcurrentInferenceRunner, BatchInferenceRunner], first_video_start_time: float = 0.0, max_loops: Optional[int] = None):
        from .config import PIPELINE_V2_CONFIG
        self.verifier_model = verifier_model
        self.verifier_fallback_model = PIPELINE_V2_CONFIG.get("stage2_verifier_fallback_model")
        self.retriever_model = PIPELINE_V2_CONFIG.get("stage2_retriever_model", "gemini-2.5-flash")
        self.retriever_fallback_model = PIPELINE_V2_CONFIG.get("stage2_retriever_fallback_model")
        self.enhancer_model = PIPELINE_V2_CONFIG.get("stage2_enhancer_model", "gemini-2.5-flash")
        self.enhancer_fallback_model = PIPELINE_V2_CONFIG.get("stage2_enhancer_fallback_model")
        self.inference_manager = inference_manager
        self.first_video_start_time = first_video_start_time

    def process(self, qa_pairs: List[Dict[str, Any]], super_ledger_dict: Dict[str, Any], super_ledger_text: str, video_paths_map: Dict[str, str], all_video_ids: List[str], output_folder: Optional[str] = None, force_reprocess: bool = False, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Run verification and enhancement on all QA pairs."""
        from google.genai import types
        verified_pairs = []
        rejected_pairs = []
        
        retriever_results = []
        verifier_results = []
        enhancer_results = []

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                duration = super_ledger_dict.get('total_duration', 0)
                video_offsets = {
                    strip_ext(v.get('video_id')): float(v.get('start_time', 0.0)) - self.first_video_start_time
                    for v in super_ledger_dict.get('videos', [])
                    if v.get('video_id') is not None
                }
                
                video_meta = {
                    strip_ext(v['video_id']): {'start_time': v.get('start_time', 0.0), 'duration': v.get('duration', 0.0)}
                    for v in super_ledger_dict.get('videos', []) if v.get('video_id')
                }
                
                # Setup storage: Use output_folder/clips if available, else temp_dir
                clips_dir = os.path.join(output_folder, "clips") if output_folder else temp_dir
                if output_folder:
                    os.makedirs(clips_dir, exist_ok=True)
                
                # 0. RETRIEVAL PHASE
                retriever_file = os.path.join(output_folder, "intermediary_retriever.json") if output_folder else None
                retriever_results = []
                if retriever_file and os.path.exists(retriever_file) and not force_reprocess:
                    logger.info(f"Resuming: Loading intermediary Retriever results from {retriever_file}")
                    with open(retriever_file, 'r') as f:
                        retriever_results = json.load(f)
                else:
                    retriever_system_prompt = get_video_chunk_retrieval_system_prompt(super_ledger_text=super_ledger_text)
                    
                    retriever_requests = []
                    for idx, qa in enumerate(qa_pairs):
                        prompt = get_video_chunk_retrieval_user_prompt(
                            qa_pair=qa
                        )
                        req = {
                            'agent_name': 'retriever',
                            'model_name': self.retriever_model,
                            'fallback_model_name': self.retriever_fallback_model,
                            'confidence_enabled': True,
                            'contents': [
                                types.Content(role="user", parts=[types.Part.from_text(text=retriever_system_prompt)]),
                                types.Content(role="model", parts=[types.Part.from_text(text="Understood. I have fully read the Super Ledger and all instructions. I am ready to proceed.")]),
                                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                            ],
                            'local_video_paths': [], # Text only
                            'response_schema': get_stage2_retrieval_schema(video_ids=all_video_ids, video_meta=video_meta),
                            'context': {'qa_idx': idx, 'original_idx': idx}
                        }
                        retriever_requests.append(req)
                        
                    logger.info(f"Running Retriever on {len(retriever_requests)} QA pairs...")
                    retriever_results = self.inference_manager.run_parallel(retriever_requests, sort_by_context_key='original_idx')

                    if retriever_file:
                        logger.info(f"Saving intermediary Retriever results to {retriever_file}")
                        with open(retriever_file, 'w') as f:
                            json.dump(retriever_results, f, indent=2)

                retrieved_chunks_map = {}
                for res in retriever_results:
                    if res['status'] == 'success' and res.get('output'):
                        retrieved_chunks_map[res['context']['qa_idx']] = res['output'].get('chunks', [])

                # 1. VERIFICATION PHASE
                verifier_file = os.path.join(output_folder, "intermediary_verifier.json") if output_folder else None
                verifier_results = []
                if verifier_file and os.path.exists(verifier_file) and not force_reprocess:
                    logger.info(f"Resuming: Loading intermediary Verifier results from {verifier_file}")
                    with open(verifier_file, 'r') as f:
                        verifier_results = json.load(f)
                else:
                    from .config import PIPELINE_V2_CONFIG
                    min_conf = PIPELINE_V2_CONFIG.get("min_confidence", 0.7)
                    verifier_system_prompt = get_verifier_system_prompt(super_ledger_text=super_ledger_text, threshold=min_conf)

                    verifier_requests = []
                    for idx, qa in enumerate(qa_pairs):
                        # Always pass the full superledger, and process relevant videos.
                        # Find which videos to extract
                        clips_to_upload = []
                        question_info = qa.get('question', {})
                        q_video = question_info.get('video_id')
                        # time_spans is now a list; backwards-compat with legacy time_span
                        q_time_spans = question_info.get('time_spans', [])
                        if not q_time_spans:
                            if 'time_span' in question_info:
                                raise ValueError(f"QA pair uses legacy 'time_span' field. Migrate to 'time_spans' list.")
                        
                        # Find absolute time of earliest question span for timing comparisons
                        q_start_abs = None
                        for span in q_time_spans:
                            q_s, _ = _get_span_bounds(span)
                            q_s_sec = _to_seconds(q_s)
                            if q_s_sec is not None:
                                abs_t = (self.first_video_start_time + video_offsets.get(q_video, 0.0) + q_s_sec)
                                if q_start_abs is None or abs_t < q_start_abs:
                                    q_start_abs = abs_t
                        
                        def queue_clip(vid, start_val, end_val, desc, priority: int = 3):
                            vid = strip_ext(vid)
                            if vid and start_val is not None and end_val is not None and vid in video_paths_map:
                                start_sec = _to_seconds(start_val)
                                end_sec = _to_seconds(end_val)
                                if start_sec is None or end_sec is None:
                                    return
                                
                                # 1. Bound check against video duration
                                meta = video_meta.get(vid, {})
                                duration = meta.get('duration', 0.0)
                                if duration > 0:
                                    if start_sec >= duration:
                                        logger.warning(f"Skipping clip {vid} [{start_val}-{end_val}] because start {start_sec:.1f}s is beyond video duration {duration:.1f}s")
                                        return
                                    if end_sec > duration:
                                        logger.info(f"Clipping end of {vid} from {end_val} to {duration:.1f}s")
                                        end_sec = duration
                                        end_val = f"{duration:.2f}"
                                
                                # 2. Enforce duration limit
                                max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120.0)
                                if end_sec - start_sec > max_dur:
                                    logger.warning(f"Clip {vid} [{start_val}-{end_val}] exceeds {max_dur}s limit. Truncating to first {max_dur}s.")
                                    end_sec = start_sec + max_dur
                                    end_val = f"{end_sec:.2f}"
                                
                                if end_sec <= start_sec:
                                    logger.warning(f"Skipping clip {vid} [{start_val}-{end_val}] because duration is non-positive.")
                                    return

                                # Compute absolute times for agent context
                                vid_offset = video_offsets.get(vid, 0.0)
                                abs_start = self.first_video_start_time + vid_offset + start_sec
                                abs_end = self.first_video_start_time + vid_offset + end_sec
                                
                                out_path = get_or_extract_clip(vid, video_paths_map[vid], start_sec, end_sec, clips_dir)
                                if not out_path:
                                    return
                                
                                clips_to_upload.append({
                                    'path': out_path, 
                                    'desc': desc, 
                                    'vid': vid, 
                                    'ts': f"{start_val}-{end_val}",
                                    'abs_time': f"{_format_abs_time(abs_start)} to {_format_abs_time(abs_end)}",
                                    'start_sec': start_sec,
                                    'priority': priority
                                })

                        # Queue question clips (one per span)
                        for span in q_time_spans:
                            q_start_local, q_end_local = _get_span_bounds(span)
                            if q_start_local is not None and q_end_local is not None:
                                span_vid = span.get('video_id') or q_video
                                queue_clip(span_vid, q_start_local, q_end_local, "Question Context", priority=1)

                        # Queue evidence clips
                        for ev in qa.get('answer', {}).get('evidence_list', []):
                            ts = ev.get('time_span', {})
                            ev_start, ev_end = _get_span_bounds(ts)
                            if ev_start is not None and ev_end is not None:
                                queue_clip(ev.get('video_id'), ev_start, ev_end, "Answer Evidence", priority=2)

                        # Queue retriever suggested chunks
                        retrieved_chunks = retrieved_chunks_map.get(idx, [])
                        video_chunks_summary_lines = []
                        if retrieved_chunks:
                            video_chunks_summary_lines.append("Chunks explicitly retrieved by Retriever:")
                            for chunk in retrieved_chunks:
                                vid = chunk.get('video_id')
                                c_start = chunk.get('start_time')
                                c_end = chunk.get('end_time')
                                reason = chunk.get('relevance_reason', 'No reason provided')
                                timing_note = ""
                                c_vid_offset = video_offsets.get(vid, 0.0)
                                c_start_sec = _to_seconds(c_start)
                                c_end_sec = _to_seconds(c_end)
                                abs_info = ""
                                if c_start_sec is not None:
                                    c_start_abs = self.first_video_start_time + c_vid_offset + c_start_sec
                                    c_end_abs = self.first_video_start_time + c_vid_offset + (c_end_sec if c_end_sec is not None else c_start_sec)
                                    abs_info = f" [Absolute: {_format_abs_time(c_start_abs)} to {_format_abs_time(c_end_abs)}]"
                                    if q_start_abs is not None and c_start_abs > q_start_abs:
                                        timing_note = " (FUTURE relative to question; verifier-only context)"
                                video_chunks_summary_lines.append(f"- Video {vid} [Local: {c_start}s - {c_end}s]{abs_info}: {reason}{timing_note}")
                                queue_clip(vid, c_start, c_end, f"Retrieved Chunk: {reason}")
                        else:
                            video_chunks_summary_lines.append("No additional chunks retrieved.")
                        
                        video_chunks_summary = "\n".join(video_chunks_summary_lines)
                        
                        # Sort by priority then chronologically
                        clips_to_upload.sort(key=lambda x: (x.get('priority', 3), x['vid'], x['start_sec']))

                        # Deduplicate while preserving order, then slice to 10
                        final_clips = []
                        seen_paths = set()
                        for c in clips_to_upload:
                            if c['path'] not in seen_paths:
                                final_clips.append(c)
                                seen_paths.add(c['path'])
                        
                        if len(final_clips) > 10:
                            logger.info(f"Slicing Verifier context from {len(final_clips)} to 10 clips for QA idx {idx}")
                            final_clips = final_clips[:10]
                        
                        clips_to_upload = final_clips

                        # Format Video Summaries
                        video_summaries = "\n".join([
                            f"Video {i+1}: {c['desc']} (Video ID: {c['vid']}, Local: [{c['ts']}], Absolute: {c.get('abs_time', 'N/A')})"
                            for i, c in enumerate(clips_to_upload)
                        ])
                        if not video_summaries: video_summaries = "No video clips."

                        prompt = get_verifier_user_prompt(
                            qa_pair=qa,
                            context_summary=qa.get('metadata', {}).get('context_summary', {}),
                            video_chunks_summary=video_chunks_summary,
                            video_clips_summary=video_summaries
                        )
                        
                        paths = [c['path'] for c in clips_to_upload]
                        req = {
                            'agent_name': 'verifier',
                            'model_name': self.verifier_model,
                            'fallback_model_name': self.verifier_fallback_model,
                            'confidence_enabled': True,
                            'contents': [
                                types.Content(role="user", parts=[types.Part.from_text(text=verifier_system_prompt)]),
                                types.Content(role="model", parts=[types.Part.from_text(text="Understood. I have fully read the Super Ledger and all instructions. I am ready to proceed.")]),
                                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                            ],
                            'local_video_paths': paths, # Will be uploaded and naturally parsed by gemini
                            'response_schema': get_stage2_verifier_schema(video_ids=all_video_ids, video_meta=video_meta),
                            'context': {'qa': qa, 'clips': clips_to_upload, 'summaries': video_summaries, 'original_idx': idx}
                        }
                        verifier_requests.append(req)

                    logger.info(f"Running Verifier on {len(verifier_requests)} QA pairs...")
                    verifier_results = self.inference_manager.run_parallel(verifier_requests, sort_by_context_key='original_idx', job_prefix='iter1_verifier')

                    if verifier_file:
                        logger.info(f"Saving intermediary Verifier results to {verifier_file}")
                        with open(verifier_file, 'w') as f:
                            json.dump(verifier_results, f, indent=2)

                # 1.5 SORT VERIFIER RESULTS (Ensures stability even when resuming)
                verifier_results.sort(key=lambda x: x['context'].get('original_idx', 0))

                # 2. ENHANCEMENT PHASE
                enhancer_file = os.path.join(output_folder, "intermediary_enhancer.json") if output_folder else None
                enhancer_results = []
                if enhancer_file and os.path.exists(enhancer_file) and not force_reprocess:
                    logger.info(f"Resuming: Loading intermediary Enhancer results from {enhancer_file}")
                    with open(enhancer_file, 'r') as f:
                        enhancer_results = json.load(f)
                else:
                    enhancer_requests = []
                    for res in verifier_results:
                        # CRITICAL: Re-extract clips if resuming from intermediary_verifier.json
                        # because the original temp_dir is gone.
                        if 'clips' in res.get('context', {}):
                            for clip in res['context']['clips']:
                                old_path = clip['path']
                                clip_filename = os.path.basename(old_path)
                                new_path = os.path.join(temp_dir, clip_filename)
                                clip['path'] = new_path # Update to new temp path
                                if not os.path.exists(new_path):
                                    # Extract again
                                    v_id = clip['vid']
                                    ts_str = clip['ts']
                                    s_val, e_val = ts_str.split('-')
                                    s_sec = _to_seconds(s_val)
                                    e_sec = _to_seconds(e_val)
                                    if s_sec is not None and e_sec is not None and v_id in video_paths_map:
                                        logger.debug(f"Re-extracting clip {clip_filename} for Enhancement phase...")
                                        extract_clip(video_paths_map[v_id], s_sec, e_sec, new_path)

                        if res['status'] == 'error' or not res.get('output'):
                            error_msg = res.get('error', 'Unknown error during verification')
                            logger.error(f"Verification failed: {error_msg}")
                            # Fallback verification score so it's not null
                            fallback_score = {
                                "factual_correctness_reasoning": f"Verification failed unconditionally: {error_msg}",
                                "objective_correctness_reasoning": "Failed to run verifier model.",
                                "causal_answerability_reasoning": "Failed to run verifier model.",
                                "suggestions": ["Retry verification or check extracted clips."],
                                "suggested_chunks": [],
                                "factual_correctness_score": 0.0,
                                "objective_correctness_score": 0.0,
                                "causal_answerability_score": 0.0,
                                "is_correct": False,
                                "error": error_msg
                            }
                            rejected_qa = res['context']['qa']
                            if 'metadata' not in rejected_qa: rejected_qa['metadata'] = {}
                            rejected_qa['metadata']['verification_score'] = fallback_score
                            rejected_pairs.append({'qa_pair': rejected_qa, 'verification_score': fallback_score})
                            continue

                        verification_score = res['output']
                        
                        if 'confidence' in res:
                            verification_score['confidence_score'] = res['confidence'].get('score')
                            verification_score['confidence_reasoning'] = res['confidence'].get('reasoning')
                            
                        qa = res['context']['qa']
                        
                        is_correct = verification_score.get('is_correct', False)
                        suggestions = verification_score.get('suggestions', [])
                        has_suggestions = len(suggestions) > 0
                        
                        # SALVAGE LOGIC: A pair is processed if it's correct OR if it's salvageable (incorrect but has suggestions)
                        if not is_correct and not has_suggestions:
                            if 'metadata' not in qa: qa['metadata'] = {}
                            qa['metadata']['verification_score'] = verification_score
                            rejected_pairs.append({'qa_pair': qa, 'verification_score': verification_score})
                            continue
                        
                        # Determine if we should enhance
                        original_is_answerable = qa.get('answer', {}).get('is_answerable')
                        if original_is_answerable is None:
                            original_is_answerable = qa.get('question', {}).get('is_answerable', True)
                            
                        # Logic:
                        # - Enhance if it's answerable (needs text refinement)
                        # - Enhance if it's unanswerable BUT has suggestions (needs salvaging/flipping)
                        # - Skip enhancement only if it's correct AND unanswerable AND has no suggestions.
                        
                        if not original_is_answerable and not has_suggestions:
                            logger.info(f"Keeping perfect unanswerable question in video {qa.get('question', {}).get('video_id')} (skipping enhancement).")
                            final_qa = copy.deepcopy(qa)
                            final_qa['verification_score'] = verification_score
                            if 'metadata' not in final_qa: final_qa['metadata'] = {}
                            final_qa['metadata']['verification_score'] = verification_score
                            
                            try:
                                removed = _filter_causal_answer_evidence(final_qa, video_offsets, self.first_video_start_time)
                                if removed > 0:
                                    logger.info(f"Removed {removed} non-causal evidence item(s) from unanswerable question in video {final_qa.get('question', {}).get('video_id')}")
                            except ValueError as e:
                                logger.error(f"Unanswerable temporal filter error: {e}")
                                final_qa['metadata']['verification_score'] = verification_score
                                final_qa['rejection_reason'] = str(e)
                                rejected_pairs.append({'qa_pair': final_qa, 'verification_score': verification_score})
                                continue
                            
                            remaining_ev = len(final_qa.get('answer', {}).get('evidence_list', []))
                            if remaining_ev == 0:
                                logger.warning(f"All evidence was removed from unanswerable question in video {final_qa.get('question', {}).get('video_id')}. This annotation may lack context.")
                                
                            verified_pairs.append(final_qa)
                            continue

                        # Include any new "suggested_chunks" from the verifier
                        suggested_clips = []
                        new_summaries = []
                        for sc in verification_score.get('suggested_chunks', []):
                            if hasattr(sc, 'model_dump'): sc = sc.model_dump()
                            elif not isinstance(sc, dict): continue
                            
                            vid = sc.get('video_id')
                            sc_start = sc.get('start_time')
                            sc_end = sc.get('end_time')
                            if sc_start is None or sc_end is None:
                                ts = sc.get('time_span', {})
                                fallback_start, fallback_end = _get_span_bounds(ts)
                                if sc_start is None: sc_start = fallback_start
                                if sc_end is None: sc_end = fallback_end
                                
                            if vid and sc_start is not None and sc_end is not None and vid in video_paths_map:
                                start_sec = _to_seconds(sc_start)
                                end_sec = _to_seconds(sc_end)
                                if start_sec is None or end_sec is None:
                                    continue
                                
                                out_path = get_or_extract_clip(vid, video_paths_map[vid], start_sec, end_sec, clips_dir)
                                if out_path:
                                    suggested_clips.append({'path': out_path, 'vid': vid, 'start_val': sc_start, 'end_val': sc_end, 'reason': sc.get('relevance_reason', 'Verifier suggested context')})
                                    new_summaries.append(f"Video (Suggested): {sc.get('relevance_reason', 'Context suggested by verifier')} (Video ID: {vid}, Local: [{sc_start}-{sc_end}])")

                        all_paths = [c['path'] for c in res['context']['clips']] + [c['path'] for c in suggested_clips]
                        # Deduplicate paths while preserving chronological order, then slice to 10
                        all_paths = list(dict.fromkeys(all_paths))
                        
                        combined_summary = res['context']['summaries']
                        if new_summaries:
                            combined_summary += "\n" + "\n".join(new_summaries)
                        
                        if len(all_paths) > 10:
                            logger.info(f"Slicing Enhancer context from {len(all_paths)} to 10 clips for QA idx {res['context'].get('original_idx')}")
                            all_paths = all_paths[:10]

                        enhance_prompt = get_enhancer_user_prompt(
                            qa_pair=qa,
                            verification_score=verification_score,
                            video_clips_summary=combined_summary
                        )

                        enhancer_requests.append({
                            'agent_name': 'enhancer',
                            'model_name': self.enhancer_model,
                            'fallback_model_name': self.enhancer_fallback_model,
                            'confidence_enabled': True,
                            'return_confidence_metadata': True,
                            'contents': [
                                types.Content(role="user", parts=[types.Part.from_text(text=get_enhancer_system_prompt(available_video_ids=all_video_ids))]),
                                types.Content(role="model", parts=[types.Part.from_text(text="Understood. I have fully read all instructions. I am ready to proceed.")]),
                                types.Content(role="user", parts=[types.Part.from_text(text=enhance_prompt)])
                            ],
                            'local_video_paths': all_paths,
                            # Enhancer DOES NOT need the super ledger, so no cached content here
                            'response_schema': get_stage2_enhancer_schema(video_ids=all_video_ids, video_meta=video_meta),
                            'context': {'qa': qa, 'score': verification_score, 'original_idx': res['context'].get('original_idx', 0)}
                        })

                    logger.info(f"Running Enhancer on {len(enhancer_requests)} verified QA pairs...")
                    enhancer_results = self.inference_manager.run_parallel(enhancer_requests, sort_by_context_key='original_idx', job_prefix='iter1_enhancer')
                    
                    if enhancer_file:
                        logger.info(f"Saving intermediary Enhancer results to {enhancer_file}")
                        with open(enhancer_file, 'w') as f:
                            json.dump(enhancer_results, f, indent=2)

                for res in enhancer_results:
                    if res['status'] == 'error' or not res.get('output'):
                        logger.error(f"Enhancement failed: {res.get('error')}")
                        rejected_qa = res['context']['qa']
                        if 'metadata' not in rejected_qa: rejected_qa['metadata'] = {}
                        rejected_qa['metadata']['verification_score'] = res['context']['score']
                        rejected_pairs.append({'qa_pair': rejected_qa, 'verification_score': res['context']['score']})
                        continue
                    enhanced_qa = res['output']
                    
                    if 'metadata' not in enhanced_qa: enhanced_qa['metadata'] = {}
                    
                    # Move confidence from root (injected by runner) into metadata
                    if 'confidence_score' in enhanced_qa:
                        # UI historically used 'confidence' as a float or string inside metadata
                        enhanced_qa['metadata']['confidence'] = enhanced_qa.pop('confidence_score')
                    if 'confidence_reasoning' in enhanced_qa:
                        enhanced_qa['metadata']['confidence_reasoning'] = enhanced_qa.pop('confidence_reasoning')
                    
                    # Mirror score programmatically as requested
                    enhanced_qa['verification_score'] = res['context']['score']
                    # Force strictly mirrored
                    enhanced_qa['metadata']['verification_score'] = res['context']['score'] 

                    # Preserve answer_choices: if the enhancer dropped them, copy from original QA pair
                    original_qa = res['context']['qa']
                    original_choices = original_qa.get('answer', {}).get('answer_choices', [])
                    enhanced_choices = enhanced_qa.get('answer', {}).get('answer_choices', [])
                    if not enhanced_choices and original_choices:
                        if 'answer' not in enhanced_qa:
                            enhanced_qa['answer'] = {}
                        enhanced_qa['answer']['answer_choices'] = original_choices
                        logger.info(
                            f"Restored {len(original_choices)} answer_choices from original QA pair "
                            f"for question video {enhanced_qa.get('question', {}).get('video_id')}"
                        )

                    # Preserve is_answerable: if the enhancer dropped it, copy from original QA pair
                    # is_answerable lives on the answer object
                    original_is_answerable = original_qa.get('answer', {}).get('is_answerable')
                    enhanced_is_answerable = enhanced_qa.get('answer', {}).get('is_answerable')
                    if enhanced_is_answerable is None and original_is_answerable is not None:
                        if 'answer' not in enhanced_qa:
                            enhanced_qa['answer'] = {}
                        enhanced_qa['answer']['is_answerable'] = original_is_answerable
                        logger.info(
                            f"Restored is_answerable={original_is_answerable} from original QA pair "
                            f"for question video {enhanced_qa.get('question', {}).get('video_id')}"
                        )
                    # Also check legacy location (question.is_answerable) for backward compat
                    elif enhanced_is_answerable is None:
                        legacy_is_answerable = original_qa.get('question', {}).get('is_answerable')
                        if legacy_is_answerable is not None:
                            if 'answer' not in enhanced_qa:
                                enhanced_qa['answer'] = {}
                            enhanced_qa['answer']['is_answerable'] = legacy_is_answerable

                    # Preserve question_reasoning (CRITICAL: Context and Naturalness safety net)
                    original_q_reasoning = original_qa.get('question', {}).get('question_reasoning')
                    enhanced_q_reasoning = enhanced_qa.get('question', {}).get('question_reasoning')
                    if not enhanced_q_reasoning and original_q_reasoning:
                        if 'question' not in enhanced_qa:
                            enhanced_qa['question'] = {}
                        enhanced_qa['question']['question_reasoning'] = original_q_reasoning
                        logger.info(
                            f"Restored question_reasoning from original QA pair "
                            f"for question video {enhanced_qa['question'].get('video_id')}"
                        )

                    # Preserve skill to ensure metadata isn't scrambled
                    original_skill = original_qa.get('metadata', {}).get('skill')
                    if original_skill:
                        enhanced_qa['metadata']['skill'] = original_skill

                    # Enforce causal-only final answer evidence: remove any evidence from the future
                    # relative to the question timestamp (future clips may still be used for verification).
                    try:
                        removed = _filter_causal_answer_evidence(enhanced_qa, video_offsets, self.first_video_start_time)
                        if removed > 0:
                            logger.info(
                                f"Removed {removed} non-causal evidence item(s) from final answer evidence "
                                f"for question video {enhanced_qa.get('question', {}).get('video_id')}"
                            )
                        verified_pairs.append(enhanced_qa)
                    except ValueError as e:
                        logger.error(f"Enhanced pair temporal filter error: {e}")
                        enhanced_qa['metadata']['verification_score'] = res['context']['score']
                        enhanced_qa['rejection_reason'] = str(e)
                        rejected_pairs.append({'qa_pair': enhanced_qa, 'verification_score': res['context']['score']})

            except Exception as e:
                logger.error(f"Verification Stage failed: {e}", exc_info=True)

            # Statistics Reporting
            approved_answerable = sum(1 for p in verified_pairs if p.get('answer', {}).get('is_answerable', True))
            approved_unanswerable = sum(1 for p in verified_pairs if not p.get('answer', {}).get('is_answerable', True))
            rejected = len(rejected_pairs)
            total_processed = len(verified_pairs) + rejected
            remaining = len(qa_pairs) - total_processed
            
            retriever_fallbacks = sum(1 for res in retriever_results if res.get('fallback_used'))
            verifier_fallbacks = sum(1 for res in verifier_results if res.get('fallback_used'))
            enhancer_fallbacks = sum(1 for res in enhancer_results if res.get('fallback_used'))
            
            logger.info("\n" + "="*50)
            logger.info("STAGE 2 VERIFICATION & ENHANCEMENT SUMMARY")
            logger.info("-" * 50)
            logger.info(f"Approved (Answerable):   {approved_answerable}")
            logger.info(f"Approved (Unanswerable): {approved_unanswerable}")
            logger.info(f"Rejected:                {rejected}")
            logger.info(f"Remaining (Skipped):     {remaining}")
            logger.info("-" * 50)
            logger.info(f"Retriever Fallbacks:     {retriever_fallbacks}")
            logger.info(f"Verifier Fallbacks:      {verifier_fallbacks}")
            logger.info(f"Enhancer Fallbacks:      {enhancer_fallbacks}")
            logger.info("="*50 + "\n")

        return {
            'verified_pairs': verified_pairs,
            'rejected_pairs': rejected_pairs
        }
