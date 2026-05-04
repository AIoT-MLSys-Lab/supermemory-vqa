"""
Stage 2 Loop Concurrent — Handshake Verification + File API.

Uses ConcurrentInferenceRunner (Gemini File API, no Vertex AI) with the
3-step verifier–retriever handshake:
  Step 1: Verifier requests clips + captions (text-only, no ledger)
  Step 2: Retriever fulfills from cached super ledger
  Step 3: Verifier evaluates with QA + caption excerpts + video clips
"""

import copy
import json
import logging
import os
import tempfile
from typing import Dict, List, Any, Optional, Union

from google.genai import types

from .stage2 import PipelineStage2
from .concurrent_inference import ConcurrentInferenceRunner
from .config import PIPELINE_V2_CONFIG
from .common_utils import (
    strip_ext,
    to_seconds,
    format_abs_time,
    filter_causal_answer_evidence,
    get_or_extract_clip,
    extract_clip,
    preserve_fields_from_original,
)
from .prompts.verification import get_stage2_verifier_schema
from .prompts.enhancement import (
    get_enhancer_system_prompt,
    get_enhancer_user_prompt,
    get_stage2_enhancer_schema,
)
from .prompts.handshake_verification import (
    get_verifier_request_schema,
    get_verifier_request_system_prompt,
    get_verifier_request_user_prompt,
    get_retriever_fulfillment_schema,
    get_retriever_fulfillment_system_prompt,
    get_retriever_fulfillment_user_prompt,
    get_handshake_verifier_system_prompt,
    get_handshake_verifier_user_prompt,
)

logger = logging.getLogger(__name__)


class HandshakeVerificationStage:
    """3-step verifier–retriever handshake loop with enhancement."""

    def __init__(
        self,
        verifier_model: str,
        inference_manager: ConcurrentInferenceRunner,
        first_video_start_time: float = 0.0,
        max_loops: Optional[int] = None,
    ):
        self.verifier_model = verifier_model
        self.retriever_model = PIPELINE_V2_CONFIG.get("stage2_retriever_model", "gemini-2.5-flash")
        self.enhancer_model = PIPELINE_V2_CONFIG.get("stage2_enhancer_model", "gemini-2.5-flash")
        self.inference_manager = inference_manager
        self.first_video_start_time = first_video_start_time
        self.max_loops = max_loops if max_loops is not None else PIPELINE_V2_CONFIG.get("max_verification_loops", 3)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_clip_from_fulfilled(self, fc, video_paths_map, video_meta, video_offsets, clips_dir):
        """Extract a clip from a FulfilledClip dict."""
        vid = strip_ext(fc.get("video_id"))
        if not vid or not fc.get("available") or vid not in video_paths_map:
            return None
        start_sec = to_seconds(fc.get("start_time"))
        end_sec = to_seconds(fc.get("end_time"))
        if start_sec is None or end_sec is None or end_sec <= start_sec:
            return None

        meta = video_meta.get(vid, {})
        duration = meta.get("duration", 0.0)
        if duration > 0:
            if start_sec >= duration:
                return None
            if end_sec > duration:
                end_sec = duration

        max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
        if end_sec - start_sec > max_dur:
            end_sec = start_sec + max_dur

        out_path = get_or_extract_clip(vid, video_paths_map[vid], start_sec, end_sec, clips_dir)
        if not out_path:
            return None

        vid_offset = video_offsets.get(vid, 0.0)
        abs_start = self.first_video_start_time + vid_offset + start_sec
        abs_end = self.first_video_start_time + vid_offset + end_sec

        return {
            "path": out_path, "vid": vid,
            "start_sec": start_sec, "end_sec": end_sec,
            "start_val": fc.get("start_time"), "end_val": fc.get("end_time"),
            "abs_time": f"{format_abs_time(abs_start)} to {format_abs_time(abs_end)}",
            "desc": fc.get("relevance_note", "Retrieved clip"),
            "purpose": fc.get("purpose", "Unknown"),
        }

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self, output_folder: Optional[str]) -> Optional[str]:
        if not output_folder:
            return None
        ckpt_dir = os.path.join(output_folder, ".checkpoint")
        os.makedirs(ckpt_dir, exist_ok=True)
        return os.path.join(ckpt_dir, "handshake_checkpoint.json")

    def _save_checkpoint(
        self,
        path: Optional[str],
        iteration: int,
        verified_pile: list,
        rejected_pile: list,
        pending_verification: list,
        pending_enhancement: list,
        completed_step: int = 0,
        step_results: Optional[dict] = None,
    ):
        """Save loop state so we can resume after a crash.
        
        completed_step tracks progress within an iteration:
            0 = iteration not started
            1 = step 1 (verifier request) done
            2 = step 2 (retriever fulfillment) done
            3 = step 3 (verifier evaluation) done
            4 = enhancement done (full iteration complete)
        """
        if not path:
            return
        # pending_enhancement items contain clip dicts with local paths that
        # are non-serialisable or stale across restarts.  Strip them and
        # keep only the QA + score — clips will be re-extracted on resume.
        serialisable_enh = []
        for item in pending_enhancement:
            serialisable_enh.append({
                "qa": item["qa"],
                "score": item["score"],
                "summaries": item.get("summaries", ""),
            })
        state = {
            "completed_iteration": iteration if completed_step >= 4 else iteration - 1,
            "current_iteration": iteration,
            "completed_step": completed_step,
            "verified_pile": verified_pile,
            "rejected_pile": rejected_pile,
            "pending_verification": pending_verification,
            "pending_enhancement": serialisable_enh,
        }
        # Save intermediate step results so we can resume mid-iteration
        if step_results:
            state["step_results"] = step_results
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, path)  # atomic on POSIX
            logger.info(f"Checkpoint saved: iter {iteration} step {completed_step} → {path}")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def _load_checkpoint(self, path: Optional[str]) -> Optional[dict]:
        """Load a previous checkpoint if it exists."""
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            logger.info(
                f"Resuming from checkpoint (completed iter {state.get('completed_iteration', '?')}): "
                f"{len(state.get('verified_pile', []))} verified, "
                f"{len(state.get('rejected_pile', []))} rejected, "
                f"{len(state.get('pending_verification', []))} pending-ver, "
                f"{len(state.get('pending_enhancement', []))} pending-enh"
            )
            return state
        except Exception as e:
            logger.warning(f"Failed to load checkpoint {path}: {e}. Starting fresh.")
            return None

    def _delete_checkpoint(self, path: Optional[str]):
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Checkpoint file removed: {path}")
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process(
        self,
        qa_pairs: List[Dict[str, Any]],
        super_ledger_dict: Dict[str, Any],
        super_ledger_text: str,
        video_paths_map: Dict[str, str],
        all_video_ids: List[str],
        output_folder: Optional[str] = None,
        force_reprocess: bool = False,
        target_annotations: Optional[int] = None,
        qa_generator_func=None,
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        verified_pile: list = []
        rejected_pile: list = []
        pending_verification = qa_pairs
        pending_enhancement: list = []
        start_iteration = 1

        videos = super_ledger_dict.get("videos", [])
        video_offsets = {
            strip_ext(v.get("video_id")): float(v.get("start_time", 0.0)) - self.first_video_start_time
            for v in videos if v.get("video_id") is not None
        }
        video_meta = {
            strip_ext(v["video_id"]): {"start_time": v.get("start_time", 0.0), "duration": v.get("duration", 0.0)}
            for v in videos if v.get("video_id")
        }

        ckpt_path = self._checkpoint_path(output_folder)

        # ── Resume from checkpoint ────────────────────────────────────
        resume_step = 0
        resume_step_results: dict = {}
        if not force_reprocess:
            ckpt = self._load_checkpoint(ckpt_path)
            if ckpt:
                verified_pile = ckpt.get("verified_pile", [])
                rejected_pile = ckpt.get("rejected_pile", [])
                pending_verification = ckpt.get("pending_verification", [])
                # Restore pending_enhancement with empty clips (re-extracted later)
                pending_enhancement = [
                    {"qa": it["qa"], "score": it["score"],
                     "context_clips": [], "summaries": it.get("summaries", "")}
                    for it in ckpt.get("pending_enhancement", [])
                ]
                completed_step = ckpt.get("completed_step", 0)
                if completed_step >= 4:
                    # Full iteration completed — start next
                    start_iteration = ckpt.get("current_iteration", ckpt.get("completed_iteration", 0)) + 1
                    resume_step = 0
                else:
                    # Mid-iteration resume — restart this iteration from the next step
                    start_iteration = ckpt.get("current_iteration", ckpt.get("completed_iteration", 0) + 1)
                    resume_step = completed_step
                    resume_step_results = ckpt.get("step_results", {})
                    logger.info(f"Resuming iteration {start_iteration} from step {resume_step + 1}")
                if start_iteration > self.max_loops:
                    logger.info("Checkpoint shows all iterations complete. Returning cached results.")
                    self._delete_checkpoint(ckpt_path)
                    return {"verified_pairs": verified_pile, "rejected_pairs": rejected_pile}

        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = os.path.join(output_folder, "clips") if output_folder else temp_dir
            if output_folder:
                os.makedirs(clips_dir, exist_ok=True)

            try:
                # Assign IDs (idempotent — safe on resume)
                for idx, qa in enumerate(qa_pairs):
                    qa.setdefault("metadata", {})
                    qa["metadata"].setdefault("qa_id", f"qa_{idx}")
                    qa["metadata"]["original_idx"] = idx

                min_conf = PIPELINE_V2_CONFIG.get("min_confidence", 0.7)

                # Prompts that stay constant across iterations
                step1_sys = get_verifier_request_system_prompt()
                step2_sys = get_retriever_fulfillment_system_prompt(super_ledger_text=super_ledger_text)
                step3_sys = get_handshake_verifier_system_prompt(threshold=min_conf)
                enhancer_sys = get_enhancer_system_prompt(available_video_ids=all_video_ids)

                for iteration in range(start_iteration, self.max_loops + 1):
                    # ── DYNAMIC QA REPLENISHMENT ──
                    if target_annotations is not None and qa_generator_func is not None:
                        current_count = len(verified_pile) + len(pending_verification) + len(pending_enhancement)
                        shortfall = target_annotations - current_count
                        if shortfall > 0:
                            logger.info(f"Iter {iteration}: Detected shortfall of {shortfall} QA pairs. Generating more...")
                            try:
                                new_qas = qa_generator_func(shortfall)
                                if new_qas:
                                    offset = len(qa_pairs)
                                    for i, nqa in enumerate(new_qas):
                                        nqa.setdefault("metadata", {})
                                        nqa["metadata"].setdefault("qa_id", f"qa_{offset + i}")
                                        nqa["metadata"]["original_idx"] = offset + i
                                    qa_pairs.extend(new_qas)
                                    pending_verification.extend(new_qas)
                                    logger.info(f"Iter {iteration}: Added {len(new_qas)} new QA pairs to pending verification.")
                            except Exception as e:
                                logger.error(f"Iter {iteration}: Failed to generate QA pairs: {e}")

                    if not pending_verification and not pending_enhancement:
                        logger.info(f"Iteration {iteration}: Both queues empty. Early exit.")
                        break

                    logger.info(f"=== LOOP ITERATION {iteration}/{self.max_loops} ===")
                    logger.info(f"Pending Verification: {len(pending_verification)}")
                    logger.info(f"Pending Enhancement: {len(pending_enhancement)}")

                    failed_ver_retry: list = []
                    failed_enh_retry: list = []

                    # ══════════════════════════════════════════
                    # STEP 1: Verifier Information Request
                    # ══════════════════════════════════════════
                    if pending_verification:
                        ver_items_map = {qa.get("metadata", {}).get("qa_id", "?"): qa for qa in pending_verification}

                        # Skip step 1 if already completed in a previous run
                        is_resuming_iteration = (iteration == start_iteration and resume_step >= 1)
                        if is_resuming_iteration:
                            logger.info(f"Iter {iteration} Step 1: Skipped (resumed from checkpoint)")
                            step1_results = resume_step_results.get("step1", [])
                        else:
                            step1_requests = []
                            for idx, qa in enumerate(pending_verification):
                                qa_id = qa.get("metadata", {}).get("qa_id", "?")
                                prompt = get_verifier_request_user_prompt(qa_pair=qa)
                                step1_requests.append({
                                    "agent_name": f"iter{iteration}_step1",
                                    "model_name": self.verifier_model,
                                    "fallback_model_name": None,
                                    "confidence_enabled": False,
                                    "contents": [
                                        types.Content(role="user", parts=[types.Part.from_text(text=step1_sys)]),
                                        types.Content(role="model", parts=[types.Part.from_text(text="Understood. I am ready to analyze the QA pair.")]),
                                        types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                                    ],
                                    "local_video_paths": [],
                                    "response_schema": get_verifier_request_schema(video_ids=all_video_ids),
                                    "context": {"qa_id": qa_id, "original_idx": qa.get("metadata", {}).get("original_idx", idx)},
                                })

                            logger.info(f"Iter {iteration} Step 1: Running verifier info requests ({len(step1_requests)})...")
                            step1_results = self.inference_manager.run_parallel(step1_requests, sort_by_context_key="original_idx", job_prefix=f"iter{iteration}_s1")

                            # Checkpoint after step 1
                            # Save step 1 outputs (serialisable dicts only)
                            s1_serialisable = [
                                {"context": r["context"], "status": r["status"],
                                 "output": r.get("output"), "error": r.get("error")}
                                for r in step1_results
                            ]
                            self._save_checkpoint(
                                ckpt_path, iteration,
                                verified_pile, rejected_pile,
                                pending_verification, pending_enhancement,
                                completed_step=1,
                                step_results={"step1": s1_serialisable},
                            )

                        # ══════════════════════════════════════════
                        # STEP 2: Retriever Fulfillment
                        # ══════════════════════════════════════════
                        is_resuming_s2 = (iteration == start_iteration and resume_step >= 2)
                        if is_resuming_s2:
                            logger.info(f"Iter {iteration} Step 2: Skipped (resumed from checkpoint)")
                            step2_results = resume_step_results.get("step2", [])
                        else:
                            step2_requests = []
                            for res in step1_results:
                                if res["status"] == "error" or not res.get("output"):
                                    continue

                                qa_id = res["context"].get("qa_id")
                                qa = ver_items_map.get(qa_id)
                                if not qa:
                                    continue

                                verifier_request = res["output"]
                                if hasattr(verifier_request, "model_dump"):
                                    verifier_request = verifier_request.model_dump()

                                prompt = get_retriever_fulfillment_user_prompt(
                                    verifier_request=verifier_request,
                                )

                                contents = [
                                    types.Content(role="user", parts=[types.Part.from_text(text=step2_sys)]),
                                    types.Content(role="model", parts=[types.Part.from_text(text="Understood. I have the super ledger and am ready to fulfill requests.")]),
                                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                                ]

                                step2_requests.append({
                                    "agent_name": f"iter{iteration}_step2",
                                    "model_name": self.retriever_model,
                                    "fallback_model_name": None,
                                    "confidence_enabled": False,
                                    "contents": contents,
                                    "local_video_paths": [],
                                    "response_schema": get_retriever_fulfillment_schema(video_ids=all_video_ids),
                                    "context": {"qa_id": qa_id, "original_idx": qa.get("metadata", {}).get("original_idx", 0)},
                                })

                            if step2_requests:
                                logger.info(f"Iter {iteration} Step 2: Running retriever fulfillment ({len(step2_requests)})...")
                                step2_results = self.inference_manager.run_parallel(step2_requests, sort_by_context_key="original_idx", job_prefix=f"iter{iteration}_s2")
                            else:
                                step2_results = []

                            # Checkpoint after step 2
                            s2_serialisable = [
                                {"context": r["context"], "status": r["status"],
                                 "output": r.get("output"), "error": r.get("error")}
                                for r in step2_results
                            ]
                            self._save_checkpoint(
                                ckpt_path, iteration,
                                verified_pile, rejected_pile,
                                pending_verification, pending_enhancement,
                                completed_step=2,
                                step_results={
                                    **resume_step_results,
                                    "step2": s2_serialisable,
                                },
                            )

                        # ══════════════════════════════════════════
                        # STEP 3: Verifier Evaluation (with clips)
                        # ══════════════════════════════════════════
                        is_resuming_s3 = (iteration == start_iteration and resume_step >= 3)
                        if is_resuming_s3:
                            logger.info(f"Iter {iteration} Step 3: Skipped (resumed from checkpoint)")
                            step3_results = resume_step_results.get("step3", [])
                        else:
                            step3_requests = []

                            for res in step2_results:
                                if res["status"] == "error" or not res.get("output"):
                                    continue

                                qa_id = res["context"].get("qa_id")
                                qa = ver_items_map.get(qa_id)
                                if not qa:
                                    continue

                                retriever_resp = res["output"]
                                if hasattr(retriever_resp, "model_dump"):
                                    retriever_resp = retriever_resp.model_dump()

                                # Extract clips from fulfilled_clips (model returns them in priority order)
                                clips = []
                                for fc in retriever_resp.get("fulfilled_clips", []):
                                    clip = self._make_clip_from_fulfilled(fc, video_paths_map, video_meta, video_offsets, clips_dir)
                                    if clip:
                                        clips.append(clip)
                                # Cap at top-10 by priority (model ordered most-important first)
                                if len(clips) > 10:
                                    logger.info(f"Trimming {len(clips)} valid clips to top 10 for {qa_id}")
                                    clips = clips[:10]

                                video_summaries = "\n".join([
                                    f"Video {i+1}: [Purpose: {c.get('purpose', 'Unknown')}] {c['desc']} (Video ID: {c['vid']}, Local: [{c.get('start_val')}-{c.get('end_val')}], Absolute: {c.get('abs_time', 'N/A')})"
                                    for i, c in enumerate(clips)
                                ]) or "No video clips."

                                prompt = get_handshake_verifier_user_prompt(
                                    qa_pair=qa, retriever_response=retriever_resp, video_clips_summary=video_summaries,
                                )

                                contents = [
                                    types.Content(role="user", parts=[types.Part.from_text(text=step3_sys)]),
                                    types.Content(role="model", parts=[types.Part.from_text(text="Understood. I am ready to verify.")]),
                                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                                ]

                                step3_requests.append({
                                    "agent_name": f"iter{iteration}_step3",
                                    "model_name": self.verifier_model,
                                    "fallback_model_name": None,
                                    "confidence_enabled": False,
                                    "contents": contents,
                                    "local_video_paths": [c["path"] for c in clips],
                                    "response_schema": get_stage2_verifier_schema(video_ids=all_video_ids, video_meta=video_meta),
                                    "context": {
                                        "qa_id": qa_id, "clips": clips, "summaries": video_summaries,
                                        "retriever_response": retriever_resp,
                                        "original_idx": qa.get("metadata", {}).get("original_idx", 0),
                                    },
                                })

                            if step3_requests:
                                logger.info(f"Iter {iteration} Step 3: Running verifier evaluation ({len(step3_requests)})...")
                                step3_results = self.inference_manager.run_parallel(step3_requests, sort_by_context_key="original_idx", job_prefix=f"iter{iteration}_s3")
                            else:
                                step3_results = []

                            # Process verifier results
                            pending_verification = []
                            count_perfect = 0
                            count_junk = 0
                            count_salvage = 0
                            
                            for res in step3_results:
                                if res["status"] == "error" or not res.get("output"):
                                    continue
                                    
                                qa_id = res["context"].get("qa_id")
                                qa = ver_items_map.get(qa_id)
                                if not qa:
                                    continue

                                score = res["output"]
                                is_correct = score.get("is_correct", False)
                                is_salvageable = score.get("is_salvageable", True)
                                suggestions = score.get("suggestions", [])
                                qa["metadata"]["verification_score"] = score
                                
                                if not is_correct and not is_salvageable:
                                    qa["rejection_reason"] = "Verifier explicitly marked as not salvageable"
                                    rejected_pile.append({"qa_pair": qa, "verification_score": score})
                                    count_junk += 1
                                elif not is_correct and not suggestions:
                                    qa["rejection_reason"] = "Failed verification with no suggestions (Junk)"
                                    rejected_pile.append({"qa_pair": qa, "verification_score": score})
                                    count_junk += 1
                                elif is_correct and not suggestions:
                                    ans_answerable = qa.get("answer", {}).get("is_answerable")
                                    if ans_answerable is None:
                                        ans_answerable = qa.get("question", {}).get("is_answerable", True)
                                    if not ans_answerable:
                                        try:
                                            filter_causal_answer_evidence(qa, video_offsets, self.first_video_start_time)
                                            verified_pile.append(qa)
                                            count_perfect += 1
                                        except ValueError as e:
                                            qa["rejection_reason"] = str(e)
                                            rejected_pile.append({"qa_pair": qa, "verification_score": score})
                                            count_junk += 1
                                    else:
                                        verified_pile.append(qa)
                                        count_perfect += 1
                                else:
                                    pending_enhancement.append({
                                        "qa": qa, "score": score,
                                        "context_clips": res["context"]["clips"],
                                        "summaries": res["context"]["summaries"],
                                    })
                                    count_salvage += 1
                            
                            logger.info(f"Iter {iteration} Verifier Done: Added {count_perfect} to Perfect, {count_junk} to Rejected, {count_salvage} sent to Enhancer | Current Totals: Perfect={len(verified_pile)}, Rejected={len(rejected_pile)}")

                            # Collect errors across all 3 steps
                            error_qa_ids = set()
                            for results in [step1_results, step2_results, step3_results]:
                                for res in results:
                                    if res["status"] == "error" or not res.get("output"):
                                        error_qa_ids.add(res["context"].get("qa_id"))
                            
                            failed_ver_retry = []
                            for qa_id in error_qa_ids:
                                qa = ver_items_map.get(qa_id)
                                if qa:
                                    failed_ver_retry.append(qa)
                                    logger.warning(f"Will retry {qa_id} due to API error")
                            
                            pending_verification.extend(failed_ver_retry)

                            # Checkpoint after step 3
                            s3_serialisable = [
                                {"context": r["context"], "status": r["status"],
                                 "output": r.get("output"), "error": r.get("error")}
                                for r in step3_results
                            ]
                            self._save_checkpoint(
                                ckpt_path, iteration,
                                verified_pile, rejected_pile,
                                pending_verification, pending_enhancement,
                                completed_step=3,
                                step_results={
                                    **resume_step_results,
                                    "step3": s3_serialisable,
                                },
                            )

                    # ══════════════════════════════════════════
                    # ENHANCEMENT PHASE
                    # ══════════════════════════════════════════
                    if iteration < self.max_loops and pending_enhancement:
                        enh_items_map = {it["qa"].get("metadata", {}).get("qa_id", "?"): it for it in pending_enhancement}

                        enhancer_requests = []
                        for item in pending_enhancement:
                            qa = item["qa"]
                            qa_id = qa.get("metadata", {}).get("qa_id", "?")
                            clips = item["context_clips"]

                            # Re-extract missing clips
                            for clip in clips:
                                if not os.path.exists(clip["path"]):
                                    v_id = clip["vid"]
                                    s, e = clip.get("start_sec"), clip.get("end_sec")
                                    if s is not None and e is not None and v_id in video_paths_map:
                                        extract_clip(video_paths_map[v_id], s, e, clip["path"])

                            prompt = get_enhancer_user_prompt(
                                qa_pair=qa, verification_score=item["score"], video_clips_summary=item["summaries"],
                            )
                            contents = [
                                types.Content(role="user", parts=[types.Part.from_text(text=enhancer_sys)]),
                                types.Content(role="model", parts=[types.Part.from_text(text="Understood. Ready to enhance.")]),
                                types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                            ]
                            enhancer_requests.append({
                                "agent_name": f"iter{iteration}_enhancer",
                                "model_name": self.enhancer_model,
                                "fallback_model_name": None,
                                "confidence_enabled": False,
                                "contents": contents,
                                "local_video_paths": [c["path"] for c in clips],
                                "response_schema": get_stage2_enhancer_schema(video_ids=all_video_ids, video_meta=video_meta),
                                "context": {"qa_id": qa_id, "original_idx": qa.get("metadata", {}).get("original_idx", 0)},
                            })

                        logger.info(f"Iter {iteration}: Running Enhancer on {len(enhancer_requests)} QA pairs...")
                        enh_results = self.inference_manager.run_parallel(enhancer_requests, sort_by_context_key="original_idx", job_prefix=f"iter{iteration}_enh")

                        pending_enhancement = []
                        for res in enh_results:
                            qa_id = res["context"].get("qa_id")
                            item = enh_items_map.get(qa_id)
                            if not item:
                                continue
                            qa = item["qa"]

                            if res["status"] == "error" or not res.get("output"):
                                logger.error(f"Enhancement failed for {qa_id}: {res.get('error')}")
                                failed_enh_retry.append(item)
                                continue

                            enhanced_qa = res["output"]
                            if not isinstance(enhanced_qa, dict):
                                failed_enh_retry.append(item)
                                continue

                            enhanced_qa.setdefault("metadata", {})["qa_id"] = qa_id
                            preserve_fields_from_original(enhanced_qa, qa)

                            try:
                                filter_causal_answer_evidence(enhanced_qa, video_offsets, self.first_video_start_time)
                                if "metadata" in enhanced_qa:
                                    enhanced_qa["metadata"].pop("verification_score", None)
                                pending_verification.append(enhanced_qa)
                            except ValueError as e:
                                enhanced_qa["rejection_reason"] = str(e)
                                rejected_pile.append({"qa_pair": enhanced_qa, "verification_score": item["score"]})

                    # Retry failed items
                    pending_verification.extend(failed_ver_retry)
                    pending_enhancement.extend(failed_enh_retry)

                    # Max loops fallback
                    if iteration == self.max_loops and (pending_verification or pending_enhancement):
                        logger.warning(f"Max loops ({self.max_loops}) reached. Processing remaining items.")
                        for qa in pending_verification:
                            qa["rejection_reason"] = "max_loops_exhausted"
                            rejected_pile.append({"qa_pair": qa, "verification_score": qa.get("metadata", {}).get("verification_score")})
                        for item in pending_enhancement:
                            qa = item["qa"]
                            qa["rejection_reason"] = "max_loops_exhausted"
                            rejected_pile.append({"qa_pair": qa, "verification_score": item.get("score")})
                        pending_verification = []
                        pending_enhancement = []

                    # ── Save checkpoint after each full iteration ─────
                    self._save_checkpoint(
                        ckpt_path, iteration,
                        verified_pile, rejected_pile,
                        pending_verification, pending_enhancement,
                        completed_step=4,
                    )
                    # Reset resume state after first iteration completes
                    resume_step = 0
                    resume_step_results = {}

            except Exception as e:
                logger.error(f"Handshake Verification failed: {e}", exc_info=True)
                raise

            logger.info(f"\n{'='*50}")
            logger.info("HANDSHAKE VERIFICATION SUMMARY")
            logger.info(f"Approved: {len(verified_pile)} | Rejected: {len(rejected_pile)}")
            logger.info(f"{'='*50}\n")

        # Clean up checkpoint on successful completion
        self._delete_checkpoint(ckpt_path)

        return {"verified_pairs": verified_pile, "rejected_pairs": rejected_pile}


# ══════════════════════════════════════════════════════════════════════
# Pipeline class
# ══════════════════════════════════════════════════════════════════════

class PipelineStage2LoopConcurrent(PipelineStage2):
    """Stage 2 with concurrent File API inference + handshake verification.

    Inherits from PipelineStage2 (which uses ConcurrentInferenceRunner + GEMINI_API_KEY).
    Overrides _get_verifier_stage to use HandshakeVerificationStage.
    """

    def _get_verifier_stage(self, first_video_start_time: float, max_loops: Optional[int] = None):
        return HandshakeVerificationStage(
            verifier_model=self.verifier_model,
            inference_manager=self.inference_manager,
            first_video_start_time=first_video_start_time,
            max_loops=max_loops,
        )


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import typer
    from typing_extensions import Annotated

    app = typer.Typer(add_completion=False, help="Stage 2 QA with Concurrent File API + Handshake Verifier")

    @app.command()
    def run_cli(
        narration_folder: Annotated[str, typer.Argument(help="Folder with narration files")],
        video_folder: Annotated[str, typer.Argument(help="Folder with original videos")],
        output_folder: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
        planner_model: Annotated[Optional[str], typer.Option("--planner-model")] = None,
        verifier_model: Annotated[Optional[str], typer.Option("--verifier-model")] = None,
        target_annotations: Annotated[Optional[int], typer.Option("--target", "-t")] = None,
        qa_per_minute: Annotated[Optional[float], typer.Option("--qa-per-minute", "-qpm")] = None,
        global_qa_ratio: Annotated[float, typer.Option("--global-qa-ratio", "-g")] = 0.5,
        qa_file: Annotated[Optional[str], typer.Option("--qa-file")] = None,
        file_pattern: Annotated[str, typer.Option("--file-pattern")] = "*_caption_narrations*.json",
        generate_only: Annotated[bool, typer.Option("--generate-only")] = False,
        ledger_only: Annotated[bool, typer.Option("--ledger-only", "-l")] = False,
        max_loops: Annotated[Optional[int], typer.Option("--max-loops")] = None,
        force: Annotated[Optional[bool], typer.Option("--force", "-f")] = None,
    ):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        try:
            stage = PipelineStage2LoopConcurrent(planner_model=planner_model, verifier_model=verifier_model)
            stage.run(
                narration_folder=narration_folder, video_folder=video_folder,
                output_folder=output_folder, target_annotations=target_annotations,
                qa_per_minute=qa_per_minute, qa_file=qa_file, file_pattern=file_pattern,
                global_qa_ratio=global_qa_ratio, stop_at_generation=generate_only,
                stop_at_ledger=ledger_only, max_loops=max_loops, force_reprocess=force,
            )
        except Exception as e:
            logger.error(f"Stage 2 Loop Concurrent failed: {e}", exc_info=True)
            raise typer.Exit(code=1)

    app()
