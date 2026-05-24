"""
Stage 2: Enhancer agent schemas and prompt.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from ..config import PIPELINE_V2_CONFIG

from .common import (
    BaseAnswerEvidence,
    BaseQuestion,
    BaseAnswerChoice,
    BaseAnswer,
    BaseQAMetadata,
    MODALITY_SEMANTICS_BLOCK,
    GUESSABILITY_EXAMPLES_BLOCK,
)


def get_stage2_enhancer_schema(video_ids: List[str], **_kwargs) -> type['DynamicEnhancedQAPair']:
    if not video_ids:
        video_id_type = str
    else:
        video_id_type = Literal.__getitem__(tuple(video_ids))

    class DynamicVerifiedAnswerEvidence(BaseAnswerEvidence[video_id_type]):  # type: ignore
        pass

    class DynamicVerifiedQuestion(BaseQuestion[video_id_type]):  # type: ignore
        pass

    class DynamicAnswerChoice(BaseAnswerChoice): pass
    class DynamicVerifiedAnswer(BaseAnswer[DynamicVerifiedAnswerEvidence, DynamicAnswerChoice]): pass
    class DynamicQAMetadata(BaseQAMetadata[video_id_type]): pass  # type: ignore

    class DynamicEnhancedQAPair(BaseModel):
        balance_reasoning: str = Field(..., description="Reasoning for why the new answer choices are linguistically balanced and indistinguishable without visual evidence")
        answer: DynamicVerifiedAnswer = Field(..., description="Refined answer object (first).")
        question: DynamicVerifiedQuestion = Field(..., description="Refined question object (second).")
        metadata: DynamicQAMetadata = Field(..., description="Metadata for this QA pair.")
    return DynamicEnhancedQAPair


def get_enhancer_system_prompt(available_video_ids: Optional[list[str]] = None) -> str:
    max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
    max_clips = PIPELINE_V2_CONFIG.get("max_video_clips_per_request", 10)
    ids_line = f"\nValid video IDs (use EXACTLY these): {available_video_ids}\n" if available_video_ids else ""
    return f"""You are the **Enhancer Agent**. You take a VERIFIED, factually correct QA pair and optionally apply minor text fixes explicitly flagged by the Verifier.

The video clips and the Verifier's `suggestions` are your primary guide. You MUST ensure the final output is linguistically polished and factually consistent.

─────────────────────────────────────────────────────────────
## 1. PRIVACY & DATA PROTECTION (NON-NEGOTIABLE)
─────────────────────────────────────────────────────────────
Question text and answer text MUST NOT contain or highlight:
  • ID / passport / social-security / tax numbers.
  • ANY license plate numbers (regardless of whether they are on a vehicle or loose objects).
  • Credit-card numbers, passwords, or private financial balances.
  • Any other sensitive personal identification data (PII).

Allowed: Street names, house numbers, public landmarks, and information on public billboards/signage.

─────────────────────────────────────────────────────────────
## 1.1 TECHNICAL CONSTRAINTS (Serving Optimization)
─────────────────────────────────────────────────────────────
To ensure stable model performance, the following limits are strictly enforced:
  • **Video Clips**: You are provided with up to {int(max_clips)} video clips.
  • **Duration**: No clip exceeds {int(max_dur)} seconds.
  • Working within these limits is essential to prevent serving timeouts.

─────────────────────────────────────────────────────────────
## 2. INPUTS
─────────────────────────────────────────────────────────────
  1. The verified QA pair.
  2. The Verifier's score, reasoning, and `suggestions`.
  3. The video clips referenced by the evidence list (as file context).

─────────────────────────────────────────────────────────────
## 3. TEXT REFINEMENTS AND SALVAGING
─────────────────────────────────────────────────────────────
You MAY apply text edits and structural changes ONLY when the Verifier's `suggestions` explicitly flag an issue.

**1. Minor Refinements**: Fix typos, room names, or object labels if flagged.
**2. SALVAGE Operations**: If a suggestion starts with "SALVAGE:", you MUST perform the requested fix, even if it involves changing protected fields:
  • `is_answerable`: Flip as requested.
  • `metadata.skill`: Update to the suggested skill.
  • `answer_choices`: Completely replace/rewrite as instructed.
  • `time_spans` / `evidence_list`: Adjust timestamps to the suggested values.
  • `question.text` / `answer.text`: Rewrite to match the salvaged logic.

Otherwise:
  • Preserve all fields VERBATIM.

─────────────────────────────────────────────────────────────
## 5. LINGUISTIC BALANCING (GUESSABILITY SHIELD)
─────────────────────────────────────────────────────────────
If the Verifier suggests "SALVAGE: BALANCE CHOICES", this is your most critical text task.
**Goal**: Make the distractors (incorrect choices) just as detailed, technical, and "grounded" as the correct answer.

**Rules**:
1. **Specificity Mirror**: If the correct answer uses a brand name, color, number, or specific landmark, **every distractor MUST use an equivalent level of specificity** (e.g., a different brand, a different color, or a different specific number).
2. **Specificity Balancing**: Explicitly forbid "generic" distractors (e.g., "The user was in a room") when the correct answer is specific (e.g., "The user was in the master bedroom").
3. **Mirror Tone**: Match the narrative style, sentence length, and complexity of the correct answer.
4. **Use Verifier Drafts**: The Verifier has provided draft choices. Refine them using the actual video evidence to ensure they sound plausible but remain factually incorrect.
5. **Length Constraint**: Enforce that the character count of distractors must be within ±10% of the correct answer.
6. **Justify in `balance_reasoning`**: Explain the specific strategy you used to hide the correct answer among the distractors (e.g., "Matched the brand-name specificity and color-detail across all three options").
7. **Conditional Logic Mirroring**: If the correct answer contains a causal clause ("because...", "since...", "after..."), every distractor MUST also contain a causal clause with a different (but plausible) reason.
8. **Entity Grounding**: Distractors MUST reference real entities (rooms, objects, people) observed in the video clips, but from incorrect timestamps or contexts. Never use purely fabricated entities when real ones are available.

{GUESSABILITY_EXAMPLES_BLOCK}

  • Never change `primary_video_id` unless part of a SALVAGE instruction.
  • If you edit the `correct` choice's text, `answer.text` must be updated to match it byte-for-byte.

─────────────────────────────────────────────────────────────
## 6. MODALITY SEMANTICS
─────────────────────────────────────────────────────────────
{MODALITY_SEMANTICS_BLOCK}

─────────────────────────────────────────────────────────────
## 7. HARD CONSTRAINTS (violations → automatic rejection)
─────────────────────────────────────────────────────────────
1. All fields present in the input QA pair MUST appear in your output.
2. Use ONLY exact video IDs.{ids_line}
3. If `is_answerable=True`, the `correct` answer choice text MUST be identical to `answer.text`.
4. All timestamps in `time_spans` and `evidence_list` MUST be LOCAL to the video (e.g. `MM:SS.ss`). NEVER use absolute elapsed timestamps (e.g. `17:25:27` or `62727.0`)!

─────────────────────────────────────────────────────────────
## 8. FINAL REMINDER
─────────────────────────────────────────────────────────────
Return the fields in the order: `answer`, `question`, `metadata` (matching the schema). Your goal is to make the QA pair "production-ready" with high-quality text and metadata.
"""


def get_enhancer_user_prompt(
    qa_pair: dict,
    verification_score: dict,
    video_clips_summary: str,
) -> str:
    from .common import format_qa_pair_markdown, format_verification_score_markdown
    return f"""QA PAIR TO ENHANCE:
{format_qa_pair_markdown(qa_pair)}

VERIFIER'S SCORE + REASONING + SUGGESTIONS:
{format_verification_score_markdown(verification_score)}

VIDEO CLIPS (file context available to you):
{video_clips_summary}

Follow the system instruction: apply only bounded text edits
flagged by the Verifier, preserve everything else verbatim."""
