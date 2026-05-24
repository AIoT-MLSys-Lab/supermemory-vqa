"""
Stage 2: QA Generation (Planner) agent schemas and prompt.

Cache-friendliness contract
---------------------------
`get_stage2_qa_generation_prompt()` returns the FULL system instruction,
including the ledger text. It is intended to be passed to Gemini context
caching as the `system_instruction` of the cache. The per-batch user
prompt (`get_stage2_qa_user_prompt`) is the ONLY piece that changes
between batches and therefore must NOT reference the ledger content.
"""

import logging
import os
from copy import deepcopy
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from ..config import PIPELINE_V2_CONFIG
from .common import (
    TimeSpan,
    MODALITIES_TYPE,
    SKILL_TYPE,
    BaseAnswerEvidence,
    BaseQuestion,
    BaseAnswerChoice,
    BaseAnswer,
    BaseQAMetadata,
    MODALITY_SEMANTICS_BLOCK,
    GUESSABILITY_EXAMPLES_BLOCK,
)


_logger = logging.getLogger(__name__)


def _to_sec(ts: str) -> float:
    """Convert MM:SS or HH:MM:SS to seconds."""
    parts = str(ts).split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(ts)
    except (ValueError, IndexError):
        return 0.0


def _from_sec(s: float) -> str:
    """Convert seconds back to MM:SS.ss."""
    s = max(0.0, s)
    m = int(s // 60)
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"


def _strip_ext(vid: str) -> str:
    return os.path.splitext(vid)[0] if vid else vid


def _fix_temporal_issues(
    pair_data: dict,
    video_meta: Dict[str, Dict[str, float]],
) -> Optional[dict]:
    """Fix temporal issues in a raw QA-pair dict.

    Applies:
      1. Bound truncation — clamp spans to the video duration.
      2. Causal filtering — remove evidence ending after the earliest question start.

    Returns ``None`` if the pair should be discarded entirely.
    """

    def _lookup(vid: str) -> Optional[Dict[str, float]]:
        return video_meta.get(_strip_ext(vid)) or video_meta.get(vid)

    # ── Fix question spans ──────────────────────────────────────────────
    question = pair_data.get("question", {})
    q_spans = question.get("time_spans", [])
    fixed_q_spans: list = []

    for span in q_spans:
        span_vid = span.get("video_id", question.get("video_id", ""))
        meta = _lookup(span_vid)
        if not meta:
            fixed_q_spans.append(span)  # can't check, keep it
            continue

        duration = meta["duration"]
        try:
            start_sec = _to_sec(span.get("start_time", "0:00"))
            end_sec = _to_sec(span.get("end_time", "0:00"))
        except Exception:
            continue

        # 1. Truncate to bounds
        if start_sec < 0: start_sec = 0.0
        if start_sec >= duration:
            continue  # start is beyond video — discard span
        if end_sec > duration:
            end_sec = duration  # truncate to video end
        
        # 2. Truncate to duration
        max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
        if end_sec - start_sec >= max_dur:
            end_sec = start_sec + max_dur - 0.1  # strictly less than max

        if end_sec <= start_sec:
            continue  # 0-second clip after truncation

        span["start_time"] = _from_sec(start_sec)
        span["end_time"] = _from_sec(end_sec)
        fixed_q_spans.append(span)

    if not fixed_q_spans:
        return None  # no valid question spans — discard pair
    question["time_spans"] = fixed_q_spans

    # ── Fix evidence spans ──────────────────────────────────────────────
    answer = pair_data.get("answer", {})
    evidence_list = answer.get("evidence_list", [])
    fixed_evidence: list = []

    for ev in evidence_list:
        ev_vid = ev.get("video_id", "")
        meta = _lookup(ev_vid)
        if not meta:
            fixed_evidence.append(ev)  # can't check, keep it
            continue

        duration = meta["duration"]
        ts = ev.get("time_span", {})
        try:
            start_sec = _to_sec(ts.get("start_time", "0:00"))
            end_sec = _to_sec(ts.get("end_time", "0:00"))
        except Exception:
            continue

        # 1. Truncate to bounds
        if start_sec < 0: start_sec = 0.0
        if start_sec >= duration:
            continue  # start is beyond video — discard evidence
        if end_sec > duration:
            end_sec = duration  # truncate to video end
        
        # 2. Truncate to duration
        max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
        if end_sec - start_sec >= max_dur:
            end_sec = start_sec + max_dur - 0.1  # strictly less than max

        if end_sec <= start_sec:
            continue  # 0-second clip after truncation

        ts["start_time"] = _from_sec(start_sec)
        ts["end_time"] = _from_sec(end_sec)
        fixed_evidence.append(ev)

    # ── Causal check ────────────────────────────────────────────────────
    if fixed_evidence and fixed_q_spans:
        min_q_abs_start = float("inf")
        for span in fixed_q_spans:
            span_vid = span.get("video_id", question.get("video_id", ""))
            meta = _lookup(span_vid)
            if meta:
                start_sec = _to_sec(span.get("start_time", "0:00"))
                abs_start = meta["start_time"] + start_sec
                min_q_abs_start = min(min_q_abs_start, abs_start)

        if min_q_abs_start < float("inf"):
            causal_ok: list = []
            for ev in fixed_evidence:
                ev_vid = ev.get("video_id", "")
                meta = _lookup(ev_vid)
                if not meta:
                    causal_ok.append(ev)  # can't verify, keep
                    continue
                end_sec = _to_sec(ev.get("time_span", {}).get("end_time", "0:00"))
                abs_end = meta["start_time"] + end_sec
                tolerance = PIPELINE_V2_CONFIG.get("temporal_tolerance_seconds", 0.5)
                if abs_end <= min_q_abs_start + tolerance:
                    causal_ok.append(ev)
                # else: causal violation — drop this evidence
            fixed_evidence = causal_ok

    # ── Cascade: answerable with no evidence → discard ──────────────────
    is_answerable = answer.get("is_answerable", True)
    if is_answerable and not fixed_evidence:
        return None

    answer["evidence_list"] = fixed_evidence
    return pair_data


def get_stage2_qa_schema(
    video_ids: List[str],
    video_meta: Optional[Dict[str, Dict[str, float]]] = None,
) -> type['DynamicQAPairList']:
    """Dynamically build Pydantic classes with video_id constrained to `video_ids`.

    Args:
        video_ids: Valid video IDs for the Literal constraint.
        video_meta: Optional mapping ``{video_id: {"start_time": float, "duration": float}}``.
            When provided, the returned schema's ``model_validator`` will
            automatically truncate out-of-bounds spans, remove causal
            violations, and salvage individually valid QA pairs from a
            partially invalid batch.
    """
    if not video_ids:
        video_id_type = str
    else:
        video_id_type = Literal.__getitem__(tuple(video_ids))

    class DynamicAnswerEvidence(BaseAnswerEvidence[video_id_type]): pass  # type: ignore
    class DynamicQuestion(BaseQuestion[video_id_type]): pass  # type: ignore
    class DynamicAnswerChoice(BaseAnswerChoice): pass
    class DynamicAnswer(BaseAnswer[DynamicAnswerEvidence, DynamicAnswerChoice]): pass
    class DynamicQAMetadata(BaseQAMetadata[video_id_type]): pass  # type: ignore

    class DynamicQAPair(BaseModel):
        answer: DynamicAnswer = Field(
            ...,
            description=(
                "The assistant's answer and supporting evidence. Generate this FIRST: "
                "facts and evidence are established before deriving a natural question. "
                "For is_answerable=False, answer.text explains why the question cannot "
                "be answered, and all three answer_choices have choice_type='incorrect'."
            ),
        )
        question: DynamicQuestion = Field(
            ...,
            description=(
                "The user-facing question and its temporal/spatial context. Generate this SECOND, "
                "after the answer and evidence are fixed. All time_spans must sit strictly "
                "chronologically AFTER every evidence time_span on the global ledger timeline. "
                "HARD REQUIREMENT: Always use first-person ('I', 'my'). For intent_recall, "
                "this is the user's trigger question, NOT an assistant's reminder."
            ),
        )
        metadata: DynamicQAMetadata = Field(
            ...,
            description=(
                "Categorization metadata. skill governs evidence requirements "
                "(timeline_reconstruction and in_context_retrieval require ≥2 evidence items). "
                "primary_video_id identifies the video in which the Question is asked for the first time."
            ),
        )

    # Capture video_meta via closure for the validator
    _video_meta = video_meta

    class DynamicQAPairList(BaseModel):
        qa_pairs: List[DynamicQAPair] = Field(
            ..., description="List of generated QA pairs matching the target annotation count"
        )

        @model_validator(mode="before")
        @classmethod
        def salvage_qa_pairs(cls, data: Any) -> Any:
            """Self-healing pre-validator that:
            1. Wraps raw lists into {"qa_pairs": [...]}
            2. Applies temporal integrity fixes when video_meta is available
            3. Validates each pair individually, keeping only valid ones
            """
            # Handle raw list from LLM
            if isinstance(data, list):
                data = {"qa_pairs": data}
            if not isinstance(data, dict):
                return data

            raw_pairs = data.get("qa_pairs", [])
            if not raw_pairs:
                return data

            valid_pairs: list = []
            temporal_fixes = 0
            for pair_data in raw_pairs:
                try:
                    # Apply temporal corrections if metadata is available
                    if _video_meta and isinstance(pair_data, dict):
                        fixed = _fix_temporal_issues(pair_data, _video_meta)
                        if fixed is None:
                            continue  # pair discarded by temporal check
                        if fixed is not pair_data:
                            temporal_fixes += 1
                        pair_data = fixed

                    # Validate individual pair — raises on failure
                    DynamicQAPair.model_validate(pair_data)
                    valid_pairs.append(pair_data)
                except Exception:
                    continue  # individual pair failed validation, skip

            if valid_pairs and len(valid_pairs) < len(raw_pairs):
                _logger.info(
                    f"Salvaged {len(valid_pairs)}/{len(raw_pairs)} valid QA pairs "
                    f"({temporal_fixes} temporal fixes applied)."
                )

            data["qa_pairs"] = valid_pairs
            return data

    return DynamicQAPairList


def _inline_json_schema_refs(schema: dict) -> dict:
    resolved = deepcopy(schema)
    defs = resolved.get("$defs", {})

    def expand(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1])
                if target is None:
                    return node
                merged = deepcopy(target)
                for k, v in node.items():
                    if k != "$ref":
                        merged[k] = expand(v)
                return expand(merged)
            return {k: expand(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [expand(x) for x in node]
        return node

    return expand(resolved)


def get_stage2_qa_json_schema(video_ids: List[str], *, inline: bool = True) -> dict:
    schema_cls = get_stage2_qa_schema(video_ids)
    js = schema_cls.model_json_schema()
    return _inline_json_schema_refs(js) if inline else js




def get_stage2_qa_generation_prompt(
    ledger_text: Optional[str] = None,
    available_video_ids: Optional[list[str]] = None,
) -> str:
    """
    Full system instruction for the Planner. Includes the ledger text so the
    whole thing can be put into a Gemini context cache. Per-batch variation
    lives in `get_stage2_qa_user_prompt`.
    """
    ids_line = f"\nValid video IDs (use EXACTLY these): {available_video_ids}\n" if available_video_ids else ""
    max_clips = PIPELINE_V2_CONFIG.get("max_video_clips_per_request", 10)
    max_clip_duration = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)

    prompt = f"""You are the **Planner Agent**. You analyze a multi-hour episodic memory ledger ("Super Ledger") produced by an AR wearable and generate high-quality, diverse Question–Answer pairs that rigorously test a future AI assistant's long-form episodic and semantic memory.

The Super Ledger is your SOLE source of truth. It is rigorously ordered chronologically by video and chunk timestamp and contains all recorded `activities`, `objects`, `people`, `visible_text`, `audio_transcript`, and `environment` fields.

─────────────────────────────────────────────────────────────
## 1. PRIVACY & DATA PROTECTION  (NON-NEGOTIABLE)
─────────────────────────────────────────────────────────────
Questions, answers, choices, and evidence MUST NOT contain or highlight:
  • ID / passport / social-security / tax numbers.
  • ANY license plate numbers (regardless of whether they are on a vehicle or loose objects).
  • Credit-card numbers, passwords, or private financial balances.
  • Any other sensitive personal identification data (PII).

Allowed: Street names, house numbers, public landmarks, and information on public billboards/signage like website addresses and phone numbers.

─────────────────────────────────────────────────────────────
## 2. ORDER OF REASONING  (CRITICAL)
─────────────────────────────────────────────────────────────
For EVERY QA pair, think in this order:
  1. **Facts first** — identify the concrete answer and locate its evidence in the ledger.
  2. **Question second** — derive a natural question that a user would ask AFTER those
     events. All `question.time_spans` must be strictly LATER than every evidence span on
     the global ledger timeline. Do not treat `question.time_spans` as a single timestamp
     by default; decide whether the same query naturally recurs in multiple later contexts.

Produce roughly the requested number of QA pairs per batch, distributed across the six
memory skills (weight toward skills whose evidence is actually present in the ledger).
For each pair, you MUST provide a **skill_reasoning** in the metadata that justifies why the
question and evidence map to the selected memory skill.

**≈ 40% of QAs per batch must be UNANSWERABLE** (`is_answerable=False`) to test the
assistant's ability to admit uncertainty instead of hallucinating.

─────────────────────────────────────────────────────────────
## 3. TECHNICAL CONSTRAINTS (FOR DOWNSTREAM VERIFIERS)
─────────────────────────────────────────────────────────────
The Verifier and Enhancer agents have strict technical limits:
  • **Clip Count**: Maximum {int(max_clips)} clips per request.
  • **Clip Duration**: Maximum {int(max_clip_duration)} seconds per clip.
Prefer generating QA pairs that can be grounded with concise evidence. Avoid evidence spans longer than the configured clip duration.

**Question Time-Span Diversity**:
  • Target roughly 15-25% of QA pairs in each batch with **multiple** `question.time_spans`.
  • A multi-span question should usually have 2-4 spans, not a long list.
  • Use multiple spans only when the exact same question would be natural at each later
    moment and the same answer remains valid at every moment.
  • Good multi-span triggers: the user repeatedly returns to the same room, repeatedly
    handles/sees the same object, repeatedly resumes the same activity, repeatedly
    meets/sees the relevant person, or has several later reminder trigger moments.
  • Bad multi-span triggers: adjacent chunks from one continuous moment, arbitrary later
    timestamps, or contexts where the user would ask a different question.
  • If only one natural trigger exists, use exactly one span. But do not collapse genuine
    recurring trigger moments into a single span.

─────────────────────────────────────────────────────────────
## 4. THE SIX MEMORY SKILLS
─────────────────────────────────────────────────────────────
**object_location_memory** — Tracking where an object was last left. Requires system to track objects and their interactions over time.
  Trigger: the user has lost something or returns to where they left it.
  "I can't seem to find my keys. Where did I leave them?" - System has to look at all the times the keys came into view and when the user interacted with it last. 
  "I don't see my mug here. Is it still in the sink?" - System has to look at all the times the user interacted with the mug and where it was last seen.

**conversational_memory** — Recalling dialogue, promises, or commitments. Requires system to keep track of conversations or monologues the user had with other people or groups over time.
  Trigger: the user wants to remember something about what was said or agreed to.
  "I will go to meet B soon. What was the address he mentioned?" - System has to look at all the times the user conversed with B and if or when the address was mentioned.
  "I forgot the name of the book A recommended. What was the name?" - System has to look at all the times the user conversed with A and if or when the book was mentioned.

**visual_recall** — High-fidelity recall of dense visual / OCR details. Requires system to recall key details in the scene from the past like signs, labels etc.
  Trigger: the user needs a specific detail they glanced at earlier.
  "I need to connect to the internet. What was the WiFi password on the whiteboard?" - System has to look at when the user user looked at the whiteboard and retrieve the correct WiFi password from there.
  "I forgot the room number I am in. What was the number on the door?" - System has to look at all the times the user user looked at the door and retrieve the correct room number from there.

**timeline_reconstruction** — Ordering events across time. Requires system to retrace through multiple related video segments to determine if something was done or not and in what order it was done in relation to other activities.
  Hard requirement: `evidence_list` has **≥2 items from ≥2 distinct time regions**.
  Natural phrasing only — NEVER "order these chronologically". Instead:
  "I am going home. Which path did I take from here?" - System has to retrace the steps the user took to come where they are now and deduce which way they should go.
  "I do not recall using milk while cooking. Can you tell me when I used it?" - System has to go over the steps when cooking and see if milk was actually used in the cooking.
  "What were all the ingredients I used in the marinade? I want to know if I missed anything." - System has go over the cooking steps and note all ingredients and compare it to the list of ingredients that were meant to be used and deduce what is missing.

**intent_recall** — Proactive, assistant-initiated reminders (see §4). Requires system to keep track of all the things the user said they intend to do or implied through their actions that they need to be reminded of something.
  Trigger: the user needs to remember something at the exact time/place/actions.
  "I am going to start folding laundry now. Is there anything I should be reminded of?" - The system needs to check all the times the user asked to be reminded of something and see if he needs to do something before folding laundry.
  "What should I be doing right now?" - The system needs to check all the times the user asked to be reminded of something and see if those reminders are relevant in the current time or place or action or context.

**in_context_retrieval** — Multi-hop reasoning chaining ≥2 facts. Requires system to connect two or more events and facts to deduce an answer. 
  Hard requirement: `evidence_list` has **≥2 items from ≥2 distinct time regions**.
  Answering requires resolving fact A to unlock lookup B.
  "Given the meeting time B mentioned, do I have time to finish the laundry I started?" - The system has to find the meeting time and the time left for the laundry to deduce the answer.
  "My bus leaves in 20 minutes. Will the dryer finish up in time?" - The system has to find the bus departure time and the time left for the dryer to finish up to deduce the answer.

─────────────────────────────────────────────────────────────
## 5. INTENT RECALL — DETAILED RULES
─────────────────────────────────────────────────────────────
For `intent_recall`, `question.text` MUST be a natural, diverse user query testing the assistant's proactive capabilities. 
  - **First-Person ONLY**: The question MUST use "I", "my", "me".
  - **User Trigger ONLY**: The question field MUST contain the user's inquiry, NOT the assistant's reminder content.
  - **No Third-Person Reporting**: Do NOT use phrases like "Person A suggested you..." as a question.
  ✗ "Is there anything the assistant should remind the user about now?" (Too repetitive)
  ✗ "Reminder: You should start chopping the chicken." (Assistant voice; violates first-person rule)
  ✓ "I'm heading out to the grocery store. Is there anything I need to pick up or do?"
  ✓ "I want to figure out my schedule. Do I have any pending tasks for this afternoon?"
  ✓ "I feel like I forgot something. Remind me what I'm supposed to be doing right now."
It MUST NOT contain the reminder content.

`question.time_spans` mark the moment the query is evaluated. The evidence is the past
moment where the intent was recorded either from the user's own words or from an inferred intent from the user's actions and context. 
For recurring reminders or repeated "do I need to do anything now?" contexts, use multiple
`question.time_spans` when the same reminder state should be evaluated at several later
times/places and the same answer remains correct for each trigger.

Generate a MIX of these four sub-types. For ALL sub-types, ensure LINGUISTIC BALANCING: all three choices must be similar in length, tone, and specificity. If the correct answer is a specific duration (e.g., "1 hour"), distractors must also be specific durations (e.g., "2 hours"), not vague ones.

**(A) Valid Reminder** — `is_answerable=True`
There is an active intent that should trigger right now.
  • correct   — States the exact reminder (e.g., "You need to buy milk; the carton was empty at 10:15 AM."). Do NOT use "Yes, the assistant should..." or "Reminder:" prefixes.
  • incorrect — MUST be semantically close to the correct choice. Use timing/location distractors (real reminders from other times), or plausible fabricated reminders that match the *intensity* and *category* of the correct one.

**(B) Mistimed/Mislocated Reminder** — `is_answerable=True`
There is no active reminder for right now, but there is a pending reminder that will trigger later.
  • correct   — Explicitly states that there is no active reminder *right now*, and clarifies exactly when/where the pending reminder will trigger.
  • incorrect — Incorrectly asserts that the pending reminder should be given *right now* (falling for the context trap).

**(C) Distractor Moment (No Reminders Due)** — `is_answerable=True`
The user asks if there are reminders, but none are recorded or pending.
  • correct   — "I don't have any reminders or tasks recorded for this afternoon."
  • vague     — "You don't have any reminders scheduled for right now."
  • incorrect — Fabrication of a plausible reminder based on general context (e.g., "You need to finish the laundry" even if not in ledger).

**(D) Unanswerable (Hallucinated Intent)** — `is_answerable=False`
The user asks about a specific intent that NEVER occurred (e.g., "What did I say about the meeting?" when no meeting was mentioned).
  • All three choices = `incorrect`, all plausible fabrications, linguistically balanced.
  • `answer.text` explains that there is no record of the user ever mentioning such an intent.

─────────────────────────────────────────────────────────────
## 6. TEMPORAL GAP REQUIREMENTS
─────────────────────────────────────────────────────────────
Gap = (earliest `question.time_spans.start_time`) − (latest evidence `end_time`),
measured on the GLOBAL ledger timeline (cross-video gaps count the real-world time
between sessions as given in the ledger headers).

Required distribution in this batch:
  • ≥ 25% CROSS-VIDEO (question.video_id differs from at least one evidence.video_id).
  • ≥ 50% gap ≥ 15 min.
  • ≈ 30% gap ≥ 45 min.
  • ≤ 10% gap < 15 min, AND only appropriate for unanswerable / hallucination probes or the the first few sessions where there is not enough context to create QA from.
  • 0% gap < 5 min. Never.

In EVERY `question_reasoning` you MUST:
  1. State the gap in minutes or hours.
  2. Cite the ABSOLUTE date+time strings from the ledger headers for BOTH the question
     span(s) and the evidence moment (e.g., "2026-03-29 18:16 → 2026-03-29 19:45 ≈ 1h29m").
  3. Justify why it is NATURAL to ask (or for the assistant to chime in) at that moment —
     the specific in-world trigger (returning to a room, seeing a related object, etc.).
  4. If `question.time_spans` contains multiple spans, justify EACH span separately and
     explain why the same question and answer are valid at all listed spans.

─────────────────────────────────────────────────────────────
## 7. QUESTION QUALITY BAR
─────────────────────────────────────────────────────────────
**Natural human voice (HARD requirement).** Every question must sound like something a
real AR-glasses wearer would actually say — curiosity, forgetfulness, or context-
triggered. Robotic or exam-style phrasing is UNACCEPTABLE.
  ✗ "Order the rooms I visited chronologically." - too robotic, unnatural.
  ✓ "I am going outside now. Did I turn off all the lights upstairs?" - user naturally would check if lights are off before going outside.
  ✗ "List all items on the desk." - too robotic, unnatural, user would never ask this.
  ✓ "I cannot find my receipt. Did I throw it out or leave it at the office?" - specific query grounded in context.
  ✗ "What did A ask me to bring on March 31st?" - real users seldom use exact dates. usually reference relative time like last week or a specific day of the week.
  ✓ "I am going to meet A tomorrow. What did he ask me to bring last week?" - relative time reference , grounded context. 
  ✗ "What did I talk about with B on March 15th?" - exact date reference 
  ✓ "I forgot what B suggested about the frames the last Sunday. What did he say about the glasses?" - relative time reference, grounded context.
  ✗ "In what order did I do the following: sweeping, mopping, dusting, vacuuming." - unnatural phrasing, should be grounded in context, not asking user to mentally recreate a list. Avoid question that directly asks "what was the order of X, Y, Z" and instead go for question that need system to order these implicitly to deduce an answer.
  ✓ "Did I mop the floor in the spare bedroom today after vacuuming?" - more realistic query.
  
**Multi-evidence reasoning.** At least 50% of QAs in the batch should have `evidence_list`
with ≥ 2 items. `timeline_reconstruction` and `in_context_retrieval` REQUIRE ≥ 2 items.

**Contextual triggering.** Questions feel most natural when anchored to what the user is
currently doing — returning to the kitchen, seeing a familiar person, reading something
related, arriving where they planned to go.  The question should match the context of when 
or where it is asked. It should feel natural for an user to ask it and most critically it 
has to be something useful and non-trivial, something that the user would actually need to 
ask or know that they cannot know by themselves with low effort.

**Recurring contextual triggers.** When the same natural trigger appears more than once
after the evidence, list each valid trigger in `question.time_spans` instead of inventing
a new QA. Examples: returning to the kitchen twice while looking for the mug; later seeing
the same person in two sessions and asking what they said earlier; repeatedly packing up
chips and asking where the case was left; multiple later moments where an active reminder
would fire. The question text must be context-independent enough to make sense at every
listed span.


─────────────────────────────────────────────────────────────
## 8. ANSWER CHOICES — EXACTLY 3
─────────────────────────────────────────────────────────────
**When `is_answerable=True`:**
  • `correct`   — precise, complete answer supported by evidence. MUST match `answer.text`.
  • `vague`     — technically not wrong but too general to be useful.
                   e.g., correct: "on the counter next to the coffee maker"
                         vague:   "somewhere in the kitchen".
  • `incorrect` — Specious, Either contradicts evidence, but plausible enough to distract or too specific in a way that is unsubstantiated by evidence.
  • It should not be possible to reliably infer the correct answer by only looking at the Question and answer choices.

{GUESSABILITY_EXAMPLES_BLOCK}

**When `is_answerable=False`:**
  • All three are `incorrect`, all plausible-sounding fabrications.
  • LINGUISTICALLY BALANCED: similar length, similar specificity, similar syntax. A
    reader inspecting only the choices must NOT be able to infer that the question is
    unanswerable. Do NOT make one choice conspicuously vague or short.

Each choice's `explanation` must justify its `choice_type` with reference to the
evidence (or to the absence of evidence, for the unanswerable case).

─────────────────────────────────────────────────────────────
## 9. UNANSWERABLE QUESTIONS — FIELD CONVENTIONS
─────────────────────────────────────────────────────────────
When `is_answerable=False`:
  • `answer.text` EXPLAINS WHY the question cannot be answered from the ledger, e.g.
    "The ledger records Mike's presence but not what he was wearing."
  • `answer.evidence_list` should point to the NEAREST related context that a naive
    system might mistake for an answer. If no related context exists, the list may be empty.
  • All three `answer_choices` are `incorrect`, linguistically balanced (see §7).

**CRITICAL: Quality of Unanswerable Fabrications & Premises**
1. **Grounded Premises**: Prefer generating unanswerable questions about REAL events or objects in the ledger where a specific detail is missing (e.g., asking what was written on a real piece of paper that was too blurry to read), rather than inventing entirely hallucinated scenarios (e.g., asking about a pizza delivery that never happened), unless specifically creating a hallucination probe.
2. **Entity Grounding**: Each fabricated choice MUST use real entities, rooms, and objects from the Super Ledger (just from wrong times/contexts). Never use purely hallucinated entities unless testing a hallucination probe.
3. **Matched Specificity**: Include specific timestamps, colors, brands, or quantities in your fabrications — never use vague hedging.
4. **Indistinguishability**: The 3 fabricated choices must read identically in style, length, and detail to a "correct" choice on an answerable question. A model must not be able to deduce the question is unanswerable just because the choices sound generic.

─────────────────────────────────────────────────────────────
## 10. EVIDENCE QUALITY — THE `reason` FIELD
─────────────────────────────────────────────────────────────
For each `evidence_list` item, `reason` MUST:
  1. Summarize the relevant description from the specific ledger fragment.
  2. Explain HOW that fragment supports the answer — do not merely restate it.
  3. Be verifiable from the ledger alone.

  ✗ "User was in the kitchen."
  ✓ "At 12:03 in vid_a, audio_transcript: 'I'll leave the keys by the toaster.' This is
     the last stated location of the keys before the question moment in vid_b."

─────────────────────────────────────────────────────────────
## 11. MODALITIES
─────────────────────────────────────────────────────────────
{MODALITY_SEMANTICS_BLOCK}

─────────────────────────────────────────────────────────────
## 12. HARD CONSTRAINTS (violations → automatic rejection)
─────────────────────────────────────────────────────────────
1. Strict anchoring: every answerable QA must be derivable from the ledger. No
   hallucinated entities, rooms, people, or events.
2. First-person framing ("I", "my") for user questions. This is a HARD REQUIREMENT for all skills. Even for intent_recall, the question field MUST be a user query (e.g., "Is there anything I should do now?"), NOT an assistant's reminder statement (e.g., "Reminder: You should...").
3. Cross-video evidence: if evidence spans multiple videos, `evidence_list` must
   explicitly include items from each relevant `video_id`.
4. Use ONLY exact video IDs present in the ledger.{ids_line}
   NEVER invent IDs.
5. Temporal grounding: `time_spans` is a LIST of one or more video-local MM:SS bounds. Target 15-25% of QA pairs with 2-4 question spans when the question would naturally recur in similar later contexts (e.g., every time the user enters a specific room). The EARLIEST `start_time` across ALL question `time_spans` must be strictly chronologically AFTER the LATEST `end_time` of ALL evidence `time_spans`. No question span may overlap any evidence span. Do not add extra spans unless the unchanged question text is natural and the unchanged answer is valid at every listed span.
6. `metadata.primary_video_id` = the video ID where the question is asked for the first time.
7. Every `question_reasoning` MUST contain the absolute-time citations and gap number
   described in §5.
8. `room` fields must use the exact phrasing from the ledger's `environment` field for
   the corresponding time region.
9. Prior Knowledge Guard: If a question asks about commonly-known facts (board game 
   rules, famous recipes, well-known brand products), the distractors MUST use OTHER 
   real rules/facts from the same domain. For example, if the correct answer is a real 
   Monopoly rule, the distractors must be OTHER real Monopoly rules (applied to the 
   wrong context), not invented rules.

─────────────────────────────────────────────────────────────
## 13. FINAL REMINDER
─────────────────────────────────────────────────────────────
Determine facts and evidence FIRST, then derive a natural question placed LATER in the
timeline. The ledger below is the ONLY ground truth.
"""

    if ledger_text:
        prompt += f"\n─────────────────────────────────────────────────────────────\n"
        prompt += "## SUPER LEDGER\n"
        prompt += "─────────────────────────────────────────────────────────────\n"
        prompt += ledger_text
        prompt += "\n"

    return prompt


def get_stage2_qa_user_prompt(
    target_annotations: int,
    batch_number: int,
    total_batches: int,
    previous_batch_summary: Optional[str] = None,
    cross_day_summary: Optional[str] = None,
) -> str:
    """Per-batch user turn. This is the ONLY content that varies between batches.

    Args:
        previous_batch_summary: Per-QA line items for QAs generated in the
            *current* context (same ledger / same day).
        cross_day_summary: Compact skill-distribution + coverage summary for
            QAs generated in *other* days / the global pass, so the model can
            avoid global skill imbalance without seeing every QA.
    """
    lines = [
        f"Generate exactly **{target_annotations}** high-quality QA pairs for this batch, following every rule in the system instruction.",
        "When the ledger contains recurring later trigger moments, include multi-span questions: roughly 15-25% of the batch should use 2-4 `question.time_spans` instead of a single span.",
        "",
        f"### Batch {batch_number} of {total_batches}",
    ]

    if cross_day_summary:
        lines += [
            "",
            "#### QAs already generated for OTHER days / global pass",
            cross_day_summary,
            "",
            "Use the above to avoid global skill imbalance. You MAY re-ask a similar question if your evidence is from a different time/video.",
        ]

    if previous_batch_summary:
        lines += [
            "",
            "#### QAs already generated in THIS context (skill | evidence | question snippet):",
            previous_batch_summary,
            "",
            "ACTIVELY PREFER:",
            "  • ledger time regions NOT yet explored,",
            "  • skills under-represented so far,",
            "  • entities / people / objects not yet referenced.",
            "Do NOT recycle question patterns from previous batches. Ensure `intent_recall` questions are diverse and contextually grounded.",
        ]
    elif not cross_day_summary:
        lines += [
            "",
            "This is the FIRST batch — establish broad coverage across the ledger's time span and all six skills.",
        ]

    return "\n".join(lines)
