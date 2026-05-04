"""
Stage 2: Video Chunk Retrieval (Retriever) agent schemas and prompt.
"""


import os
from typing import List, Literal, Union, Optional, Any
from pydantic import BaseModel, Field, model_validator
from ..config import PIPELINE_V2_CONFIG


def get_stage2_retrieval_schema(
    video_ids: List[str],
    video_meta: Optional[dict[str, dict[str, float]]] = None,
) -> type['DynamicVideoChunkList']:
    if not video_ids:
        video_id_type = str
    else:
        video_id_type = Literal.__getitem__(tuple(video_ids))

    class DynamicRelevantVideoChunk(BaseModel):
        relevance_reason: str = Field(..., description="Why this specific segment is needed to verify the QA pair. MUST include: (1) the concrete evidence check it supports (e.g., 'confirms the keys are placed on the counter at 12:03'), (2) the total duration of the source video as stated in the ledger (e.g., 'Video duration: 45:30'), and (3) confirmation that start_time and end_time fall within [0, video_duration].")
        video_id: video_id_type = Field(..., description="Video ID containing this segment")  # type: ignore
        start_time: str = Field(..., description="Segment start in MM:SS format. Must match a real caption range in the ledger — do not round or invent.")
        end_time: str = Field(..., description=f"Segment end in MM:SS format. MUST be < {PIPELINE_V2_CONFIG.get('max_clip_duration', 120)}s after start_time. Must match a real caption range in the ledger.")
        relevance_score: float = Field(..., description="How relevant this segment is (0.0–1.0). 1.0 = essential; 0.5 = useful cross-check context; <0.3 = probably should be omitted.")

    _video_meta = video_meta

    def _to_sec(ts: Union[str, float]) -> float:
        if isinstance(ts, (int, float)): return float(ts)
        parts = str(ts).split(":")
        try:
            if len(parts) == 2: return int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            return float(ts)
        except (ValueError, IndexError): return 0.0

    def _from_sec(s: float) -> str:
        s = max(0.0, s)
        m = int(s // 60)
        sec = s % 60
        return f"{m:02d}:{sec:05.2f}"

    class DynamicVideoChunkList(BaseModel):
        chunks: List[DynamicRelevantVideoChunk] = Field(
            ...,
            description=f"Relevant segments for the verifier, ordered by priority (most important first). No single segment may exceed {PIPELINE_V2_CONFIG.get('max_clip_duration', 120)}s."
        )

        @model_validator(mode="before")
        @classmethod
        def salvage_chunks(cls, data: Any) -> Any:
            if isinstance(data, list):
                data = {"chunks": data}
            if not isinstance(data, dict):
                return data

            raw_chunks = data.get("chunks", [])
            if not raw_chunks:
                return data

            valid_chunks: list = []
            for chunk_data in raw_chunks:
                if not isinstance(chunk_data, dict): continue
                
                # Apply temporal corrections if metadata is available
                vid = chunk_data.get("video_id")
                vid_key = os.path.splitext(vid)[0] if vid else vid
                if _video_meta and vid_key and vid_key in _video_meta:
                    meta = _video_meta[vid_key]
                    duration = meta["duration"]
                    try:
                        start_sec = _to_sec(chunk_data.get("start_time", 0))
                        end_sec = _to_sec(chunk_data.get("end_time", 0))
                        
                        # 1. Truncate to bounds
                        if start_sec < 0: start_sec = 0.0
                        if start_sec >= duration: continue # Skip
                        if end_sec > duration: end_sec = duration
                        
                        # 2. Truncate to duration
                        max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
                        if end_sec - start_sec >= max_dur:
                            end_sec = start_sec + (max_dur - 0.1)
                        
                        if end_sec <= start_sec: continue # Skip
                        
                        chunk_data["start_time"] = _from_sec(start_sec)
                        chunk_data["end_time"] = _from_sec(end_sec)
                    except Exception:
                        pass
                
                try:
                    # Validate individual chunk
                    DynamicRelevantVideoChunk.model_validate(chunk_data)
                    valid_chunks.append(chunk_data)
                except Exception:
                    continue

            # Limit to 10
            data["chunks"] = valid_chunks[:10]
            return data

    return DynamicVideoChunkList


def get_video_chunk_retrieval_system_prompt(super_ledger_text: str = "") -> str:
    """System instruction for the Retriever. The ledger is cacheable content."""
    max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
    base = f"""You are the **Video Chunk Retrieval Agent**. Your job is to select the specific
video segments the Verifier needs to watch in order to validate a given QA pair.

─────────────────────────────────────────────────────────────
## Inputs
─────────────────────────────────────────────────────────────
  1. The QA Pair (question, answer, evidence list, metadata).
  2. The Super Ledger metadata (available chunks and caption segments with timestamps).

─────────────────────────────────────────────────────────────
## Privacy
─────────────────────────────────────────────────────────────
Do NOT surface segments whose sole purpose is to expose private data
(ID cards, license plates of private vehicles, financial documents, passwords, etc.).
Public signage / billboards are fine.

─────────────────────────────────────────────────────────────
## Selection Principles
─────────────────────────────────────────────────────────────
**1. Exhaustiveness.** Include EVERY segment a verifier needs:
    • Every `answer.evidence_list` time_span (mandatory).
    • Every `question.time_spans` entry (mandatory — so the verifier can check that the
      question moment genuinely exists and is contextually coherent).
    • Earlier context segments needed to establish an object / person / fact
      (e.g., where an object was placed before the user left the room).
    • Cross-check segments AFTER the question moment that let the verifier detect
      contradictions or confirm consistency. These are VERIFIER-ONLY context and must
      not be treated as causal evidence.
    • Total duration of retrieved chunks should be below 20 minutes.

**2. Precision.** Only return the tight windows that matter.
    • Do NOT return an entire 120-second chunk if only a 20-second segment is relevant.
    • Use EXACTLY the caption-segment time bounds (MM:SS) printed in the ledger. Do not
      round, pad, or invent.

**3. Hard duration limit.** No single retrieved segment may exceed {int(max_dur)} seconds.
    If a relevant event spans more than {int(max_dur)}s, SPLIT it into multiple segments
    (e.g., 00:00–02:00 and 02:00–04:00), each with its own `relevance_reason`.

**4. Unanswerable QAs.** When `answer.is_answerable == False`:
    • Return the segments a naive model might mistake for an answer (the "nearest-
      neighbor" context). These allow the verifier to confirm that evidence is genuinely
      missing rather than overlooked.
    • Return an empty list ONLY if the ledger contains nothing remotely related.

**5. Prioritization when > 10 candidates or 20 minutes.** Keep at most 10 segments, prioritizing by relevance. Priority order:
    (a) Evidence spans from `answer.evidence_list`.
    (b) All `question.time_spans`.
    (c) Prior-context segments needed to understand the evidence.
    (d) Post-question cross-check segments with the highest discriminative value.
    Drop lowest-relevance items first.

**6. Video IDs.** Every `video_id` MUST exactly match an ID from the ledger. Never invent.

─────────────────────────────────────────────────────────────
## Output
─────────────────────────────────────────────────────────────
For each retrieved segment provide a `relevance_reason` that explicitly names the check
it supports, and a `relevance_score` in [0, 1].
"""
    if super_ledger_text:
        base += "\n─────────────────────────────────────────────────────────────\n"
        base += "## SUPER LEDGER (reference)\n"
        base += "─────────────────────────────────────────────────────────────\n"
        base += super_ledger_text
        base += "\n"
    return base


def get_video_chunk_retrieval_user_prompt(qa_pair: dict) -> str:
    from .common import format_qa_pair_markdown

    return f"""QA PAIR TO VERIFY:
{format_qa_pair_markdown(qa_pair)}

Select the segments the Verifier needs to watch, following the Selection Principles."""
