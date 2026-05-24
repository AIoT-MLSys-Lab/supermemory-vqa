"""
Stage 2: Handshake Verification prompts and schemas.

Implements the 3-step Verifier–Retriever handshake:
  Step 1: Verifier → InformationRequest  (QA pair only, no ledger)
  Step 2: Retriever → FulfillmentResponse (super ledger cached, returns caption excerpts)
  Step 3: Verifier → VerificationScore   (QA + caption excerpts + video clips, no ledger)
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from ..config import PIPELINE_V2_CONFIG
from .common import MODALITY_SEMANTICS_BLOCK


# ──────────────────────────────────────────────────────────────────────
# Step 1: Verifier Information Request (schemas)
# ──────────────────────────────────────────────────────────────────────

class ClipRequest(BaseModel):
    """A video segment the verifier wants to inspect."""
    target_content: str = Field(..., description="Description of the event, object, or action to find. You can mention the QA pair's timestamps as a hint (e.g. 'Look around 12:30 for the keys').")
    purpose: str = Field(
        ...,
        description=(
            "Why this specific clip is needed: 'evidence_verification', "
            "'question_context', 'cross_check', 'temporal_ordering', etc."
        ),
    )


class CaptionRequest(BaseModel):
    """A ledger caption range the verifier wants to read."""
    target_content: str = Field(..., description="Description of the event, object, or action to find. You can mention the QA pair's timestamps as a hint.")
    purpose: str = Field(
        ...,
        description="What information the verifier is looking for in these captions.",
    )


class VerifierInformationRequest(BaseModel):
    """Step 1 output: what the verifier needs to evaluate a QA pair."""
    reasoning: str = Field(
        ...,
        description=(
            "Explain why these specific clips and captions are needed. "
            "Reference the QA pair's question, evidence, and answer choices."
        ),
    )
    requested_clips: List[ClipRequest] = Field(
        ...,
        description=(
            "Video segments to extract and watch, ordered by priority (most important first). "
            "Must cover: (a) each evidence time_span, (b) the question time_span, "
            "(c) any additional context needed for cross-checking."
        ),
    )
    requested_captions: List[CaptionRequest] = Field(
        ...,
        description=(
            "Ledger caption ranges to surface as text. Can be more than the clips. "
            "Use these to verify facts, objects, conversations, and spatial context "
            "without needing to watch every second of video."
        ),
    )


def get_verifier_request_schema(video_ids: Optional[List[str]] = None) -> type:
    """Build a dynamic schema for Step 1."""
    return VerifierInformationRequest


def get_verifier_request_system_prompt() -> str:
    """Step 1: System prompt for the verifier information request phase."""
    return f"""\
You are a Verification Planning Agent for an AR memory assistant QA pipeline.

## Your Task
Given a QA pair (question, answer, evidence, choices, metadata), determine WHAT
information you need to verify it properly. You do NOT have access to the super
ledger or videos yet — you are requesting them.

## What You Must Request

Instead of requesting specific timestamps (which might be hallucinated in the QA pair), you must describe the **semantic content** you are looking for (e.g., "Find the moment the user drops the wallet"). You can provide the QA pair's timestamps as a *hint* to the Retriever (e.g., "The QA claims this happens around 12:30"), but do not assume they are correct.

### Clips (ordered by priority)
Request video clips to verify:
1. **Evidence claims** — to visually confirm the evidence described in the QA actually happens.
2. **Question context** — to verify the user's situation when the question takes place.
3. **Cross-checks** — to check whether answer choices (especially incorrect/vague ones) are plausible distractors.

Order clips from MOST to LEAST important. The most critical clips should come first.

### Captions
Request ledger caption excerpts for:
1. **Evidence context** — the full caption text surrounding the described evidence.
2. **Broader temporal context** — captions before/after the event to check causal ordering.
3. **Question location context** — what the ledger says about the user's environment.
4. **Distractor verification** — captions that could confirm or deny the incorrect answer choices.

You may request as many caption ranges as needed. Captions are text (cheap);
clips require video extraction (expensive). Use captions liberally for broad context.

{MODALITY_SEMANTICS_BLOCK}

## Output
Return a structured VerifierInformationRequest with your reasoning, requested clips, and requested captions.
"""


def get_verifier_request_user_prompt(qa_pair: dict) -> str:
    """Step 1: User prompt containing only the QA pair."""
    from .common import format_qa_pair_markdown
    return f"""\
Analyze this QA pair and request the specific video clips and ledger captions
you need to verify it.

{format_qa_pair_markdown(qa_pair)}

What clips and captions do you need to verify this QA pair?"""


# ──────────────────────────────────────────────────────────────────────
# Step 2: Retriever Fulfillment Response (schemas)
# ──────────────────────────────────────────────────────────────────────

class FulfilledClip(BaseModel):
    """Retriever's response about a requested clip."""
    video_id: str = Field(..., description="Video ID.")
    start_time: str = Field(..., description="Confirmed start time in MM:SS.")
    end_time: str = Field(..., description="Confirmed end time in MM:SS.")
    available: bool = Field(..., description="Whether this timespan exists and has content in the ledger.")
    relevance_note: str = Field(
        ...,
        description="Retriever's assessment of what this clip contains based on the ledger.",
    )
    purpose: str = Field(
        "",
        description="The original purpose requested by the verifier for this clip (e.g. 'evidence_verification', 'question_context'). Copy this from the verifier's request.",
    )


class CaptionExcerpt(BaseModel):
    """Verbatim caption excerpt from the super ledger."""
    video_id: str = Field(..., description="Video ID this excerpt is from.")
    start_time: str = Field(..., description="Start of the caption range.")
    end_time: str = Field(..., description="End of the caption range.")
    caption_text: str = Field(
        ...,
        description=(
            "Verbatim caption/segment text from the super ledger. "
            "Include the full segment description: activities, objects, environment, people, audio transcript."
        ),
    )
    segment_metadata: str = Field(
        ...,
        description=(
            "Additional metadata from the ledger segment: room/location, importance level, "
            "visible text (OCR), any gaze or trajectory data."
        ),
    )


class RetrieverFulfillmentResponse(BaseModel):
    """Step 2 output: retriever's response to the verifier's information request."""
    fulfilled_clips: List[FulfilledClip] = Field(
        ...,
        description="Response to each requested clip (confirmed timespans + availability), ordered by priority.",
    )
    caption_excerpts: List[CaptionExcerpt] = Field(
        ...,
        description=(
            "Verbatim caption excerpts from the super ledger matching the verifier's requests. "
            "Include ALL requested ranges plus any additional context the retriever deems relevant."
        ),
    )
    additional_context: str = Field(
        ...,
        description=(
            "Any extra context from the ledger the retriever thinks is relevant "
            "but wasn't explicitly requested. Use empty string if none."
        ),
    )


def get_retriever_fulfillment_schema(video_ids: List[str]) -> type:
    """Build a dynamic schema with constrained video IDs for Step 2."""
    if not video_ids:
        vid_type = str
    else:
        vid_type = Literal.__getitem__(tuple(video_ids))

    class DynFulfilledClip(BaseModel):
        video_id: vid_type = Field(..., description="Video ID.")  # type: ignore
        start_time: str = Field(..., description="Confirmed start time in MM:SS.")
        end_time: str = Field(..., description="Confirmed end time in MM:SS.")
        available: bool = Field(..., description="Whether this timespan exists in the ledger.")
        relevance_note: str = Field(..., description="What this clip contains based on the ledger.")
        purpose: str = Field("", description="Original verifier-request purpose for this clip.")

    class DynCaptionExcerpt(BaseModel):
        video_id: vid_type = Field(..., description="Video ID.")  # type: ignore
        start_time: str = Field(..., description="Start of caption range.")
        end_time: str = Field(..., description="End of caption range.")
        caption_text: str = Field(..., description="Verbatim caption text from the ledger.")
        segment_metadata: str = Field(..., description="Additional metadata from the segment.")

    class DynRetrieverFulfillment(BaseModel):
        fulfilled_clips: List[DynFulfilledClip] = Field(..., description="Clip availability responses, ordered by priority.")
        caption_excerpts: List[DynCaptionExcerpt] = Field(..., description="Caption excerpts from ledger.")
        additional_context: str = Field(..., description="Extra relevant context, or empty string if none.")

    return DynRetrieverFulfillment


def get_retriever_fulfillment_system_prompt(super_ledger_text: str) -> str:
    """Step 2: System prompt for the retriever fulfillment phase.
    
    The super ledger is embedded here as a stable prefix for caching.
    """
    max_clips = PIPELINE_V2_CONFIG.get("max_video_clips_per_request", 10)
    max_caption_excerpts = PIPELINE_V2_CONFIG.get("max_caption_excerpts_per_request", 20)
    return f"""\
You are a Retrieval Search Agent for an AR memory assistant QA pipeline.

## Your Role
You have full access to the Super Ledger (below). A Verifier agent has analyzed
a QA pair and is requesting specific video clips and caption excerpts to verify it.
The Verifier does NOT know the correct timestamps and relies on you to find them.
Your job is to fulfill those requests by:

1. **Searching for clips**: Scan the ledger to find the exact `start_time` and `end_time`
   (MM:SS) that best matches the Verifier's `target_content` description. Confirm clip
   availability and report what the segment actually contains. Keep clips tight and use
   exact ledger segment boundaries.
2. **Extracting caption text**: Copy the VERBATIM caption text from the ledger for
   the ranges you find. Include the full segment description (activities, objects,
   environment, people, audio_transcript, visible_text). Do NOT summarize or
   paraphrase — copy exactly.
3. **Adding context**: If you notice relevant information near the requested ranges
   that the verifier didn't ask for, include it as additional_context.

## Rules
- NEVER fabricate captions. Only report what is actually in the ledger.
- The Verifier may provide hints (e.g., "around 12:30"). Use these as starting points,
  but rely on your search of the ledger to find the true timestamps.
- For clip availability: mark available=False if you cannot find the requested content
  in the video ID provided.
- Caption excerpts can exceed the number of fulfilled clips (max {int(max_caption_excerpts)} vs max {int(max_clips)}).

## Super Ledger
{super_ledger_text}
"""


def get_retriever_fulfillment_user_prompt(verifier_request: dict) -> str:
    """Step 2: User prompt containing the verifier's information request."""
    lines = ["The Verifier needs the following information to verify a QA pair:", ""]

    reasoning = verifier_request.get("reasoning", "")
    if reasoning:
        lines.append(f"**Verifier's Reasoning:** {reasoning}")
        lines.append("")

    clips = verifier_request.get("requested_clips", [])
    if clips:
        lines.append("## Requested Video Clips")
        for i, c in enumerate(clips, 1):
            lines.append(f"{i}. **Target Content:** {c.get('target_content', '?')}")
            lines.append(f"   Purpose: {c.get('purpose', 'N/A')}")
        lines.append("")

    captions = verifier_request.get("requested_captions", [])
    if captions:
        lines.append("## Requested Caption Excerpts")
        for i, c in enumerate(captions, 1):
            lines.append(f"{i}. **Target Content:** {c.get('target_content', '?')}")
            lines.append(f"   Looking for: {c.get('purpose', 'N/A')}")
        lines.append("")

    lines.append("Fulfill these requests using the Super Ledger above.")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Step 3: Verifier Evaluation (modified prompts — NO super ledger)
# ──────────────────────────────────────────────────────────────────────

def get_handshake_verifier_system_prompt(threshold: float = 0.7) -> str:
    """Step 3: System prompt for the verifier evaluation phase.
    
    Unlike the original verifier, this prompt does NOT contain the super ledger.
    Instead, the verifier receives targeted caption excerpts from the retriever.
    """
    return f"""\
You are a strict QA Verification Agent for an AR (augmented reality) memory assistant.

## Your Task
Score a QA pair on factual correctness, objective quality, and causal ordering.
You will receive:
1. The QA pair (question, answer, evidence, choices, metadata)
2. **Caption excerpts** — verbatim text from the super ledger for relevant time ranges
3. **Video clips** — extracted segments for visual verification

You do NOT have the full super ledger. Use ONLY the provided caption excerpts and
video clips to verify the QA pair. If the excerpts don't contain enough information
to verify a claim, note this in your reasoning.

## Scoring Rubric (threshold: {threshold})

### 1. Factual Correctness (0.0–1.0)
- 1.0: Every claim in the answer matches the provided captions and video evidence exactly.
- 0.7: Minor discrepancy (e.g., slightly imprecise location) but core answer is correct.
- 0.3: Major factual error — contradicts the evidence or fabricates details.
- 0.0: Answer is completely unsupported or contradicted by the evidence.

### 2. Objective Correctness (0.0–1.0)
- 1.0: Question is natural, well-formed, and the answer directly addresses it.
- 0.7: Question is acceptable but could be more natural or specific.
- 0.3: Question feels test-like or forced.
- 0.0: Question is incoherent or unanswerable for a different reason than stated.

### 3. Causal Answerability (0.0–1.0)
- 1.0: Evidence strictly precedes the earliest question span in time; temporal ordering is correct.
- 0.7: Evidence mostly precedes, with minor overlap.
- 0.3: Evidence partially or mostly occurs after the question.
- 0.0: Evidence entirely post-dates the question (non-causal).
If `question.time_spans` contains multiple spans, validate EVERY span. Each listed span
must be a natural later moment for the exact same question, and the same answer must remain
valid at all listed spans. Do not penalize a good multi-span question merely for having
multiple spans; penalize only arbitrary, duplicate-adjacent, future-leaking, or
contextually unnatural spans.

### 4. Naturalness and Contextual Triggering (0.0 - 1.0)
Evaluate if the question feels like something a real AR-glasses wearer would naturally ask in their current situation.
- 1.0: Perfect naturalness. The question is highly practical, useful, contextually triggered by what the user is doing (e.g., returning to a room, needing a specific object), and is phrased exactly as a human would speak.
- 0.75: Good naturalness. Practical and generally makes sense to ask, but might lack a strong immediate contextual trigger or could be phrased slightly more naturally.
- 0.3: Weak naturalness. The question is somewhat useful but feels slightly forced, out of context for the current moment, or slightly robotic.
- 0.0: Complete failure. Utterly unnatural, robotic, or useless for a human to ask in any context.
For multiple `question.time_spans`, evaluate the trigger at every listed span. Full credit
requires recurring context: the same room/object/person/activity/reminder state appears
again, and the unchanged question still sounds natural.

### 5. Guessability Check
A QA is guessable if an evaluating model can pick the correct answer without seeing
any video, purely from the linguistic structure of the choices. Flag if ANY of the following hold:
- **Length Imbalance**: Any distractor differs in character count by more than ±10% from the correct answer.
- **Causal Logic Mismatch**: The correct answer has a causal clause ("because...", "since...", "after...") but one or more distractors do not.
- **Specificity Gap**: The correct choice uses brand names, exact colors, or precise numbers while distractors are vague or generic.
- **Entity Hallucination**: Distractors use invented entities not present in the video while the correct answer references real ones.
- **Refusal-Text Distractors**: Distractors read like AI refusals (e.g., "No, you did not use that salt") while the correct answer is a vivid narrative.
- **Vague Choice Quality**: The `vague` choice (when `is_answerable=True`) is a different factual claim instead of being genuinely general.

### 6. Privacy Audit
Check the QA pair for any prohibited personal data:
- **License Plates**: Audit for ANY alphanumeric sequences that look like vehicle plates (e.g., "EPY 4872" or ANY license plate numbers regardless of whether they are on a vehicle or loose objects).
- **PII**: Audit for ID / passport / social-security / tax numbers, credit-card numbers, passwords, private financial balances, or sensitive personal identification data.
- **Allowed**: Street names, house numbers, public landmarks, and information on public billboards/signage like website addresses and phone numbers.
- **Rules**: If `contains_pii` is `true`, you MUST set `is_correct = false` and provide a `SALVAGE: REMOVE PII` instruction.

{MODALITY_SEMANTICS_BLOCK}

### ADDITIONAL VERIFICATION RULES (FROM GENERATION)

#### A. THE SIX MEMORY SKILLS
Ensure the QA correctly embodies the claimed `metadata.skill`:
- **object_location_memory**: Tracking where an object was last left. Requires tracking objects over time. Trigger: user lost something or returns to where they left it.
- **conversational_memory**: Recalling dialogue, promises, or commitments. Trigger: user wants to remember what was said/agreed to.
- **visual_recall**: High-fidelity recall of dense visual/OCR details. Trigger: user needs a specific detail they glanced at earlier.
- **timeline_reconstruction**: Ordering events across time. MUST have ≥2 evidence items from ≥2 distinct time regions. Natural phrasing only.
- **intent_recall**: Proactive, assistant-initiated reminders. TRIGGER: user query asking for reminders or contextually needing one. HARD RULE: Question must be in FIRST-PERSON ('I', 'my') and NOT contain the reminder content.
- **in_context_retrieval**: Multi-hop reasoning chaining ≥2 facts. MUST have ≥2 evidence items from ≥2 distinct time regions.

#### B. INTENT RECALL SUB-TYPES
For `intent_recall`, verify it matches one of these profiles:
- **(A) Valid Reminder** (`is_answerable=True`): Active intent triggering right now. Correct choice states exact reminder without "Reminder:" or "Sure," prefixes. Incorrect choices are plausible/timed distractors.
- **(B) Mistimed/Mislocated** (`is_answerable=True`): Pending reminder for later. Correct choice clarifies when/where it triggers. Incorrect asserts it triggers now.
- **(C) Distractor Moment** (`is_answerable=True`): No reminders due. Correct choice confirms nothing pending.
- **(D) Unanswerable** (`is_answerable=False`): Hallucinated intent. Correct answer explains no such intent was recorded. All 3 choices are incorrect plausible fabrications.

#### C. NATURAL PHRASING EXAMPLES
Verify questions follow a natural human voice.
  ✗ "Order the rooms I visited chronologically." -> ✓ "I am going outside now. Did I turn off all the lights upstairs?"
  ✗ "List all items on the desk." -> ✓ "I cannot find my receipt. Did I throw it out or leave it at the office?"
  ✗ "What did I talk about with B on March 15th?" -> ✓ "I forgot what B suggested about the frames last Sunday. What did he say?"
  ✗ "In what order did I do the following: sweeping, mopping, dusting, vacuuming." -> ✓ "Did I mop the floor in the spare bedroom today after vacuuming?"

#### D. TEMPORAL GAP & REASONING RULES
Verify the temporal distance and reasoning:
- **Gap Requirements**: 
  - ≥ 50% should have gap ≥ 15 min. 
  - ≤ 10% gap < 15 min (only appropriate for unanswerables or initial sessions).
  - 0% gap < 5 min. (NEVER).
- **Question Reasoning**: The generation was required to cite absolute date+time strings and the exact gap in minutes/hours. Check that it does. For multiple `question.time_spans`, it must justify each span and explain why the same question/answer pair remains valid at all spans.

#### E. UNANSWERABLE QUESTIONS RULES
When `is_answerable=False`:
- `answer.text` MUST EXPLAIN WHY the question cannot be answered.
- The 3 choices MUST be linguistically balanced plausible fabrications.
- **Grounded Premises**: Ensure unanswerable questions use real events/objects from the ledger, just missing details, rather than purely hallucinated scenarios.
- **Entity Grounding**: Fabricated choices must use REAL entities from the Super Ledger (just from wrong times/contexts).

## Suggestions
If the QA pair has issues (score < {threshold} on any dimension, or guessability/PII),
provide specific SALVAGE suggestions. Tag each suggestion with one of:
- SALVAGE:BALANCE CHOICES — fix choice imbalance
- SALVAGE:FIX EVIDENCE — correct evidence references
- SALVAGE:FIX QUESTION — improve question naturalness
- SALVAGE:FIX ANSWER — correct answer text
- SALVAGE:ADJUST TIMESTAMPS — remove or correct invalid `question.time_spans` or evidence spans. For multi-span questions, preserve valid extra question spans and only remove the spans that fail.

If the QA pair is fundamentally broken (e.g. severe hallucination) and CANNOT be salvaged, you MUST set `is_salvageable = False` and provide an empty `suggestions` list.

## Constraints
- When suggesting timestamp edits, you MUST ONLY suggest LOCAL video timestamps (e.g. `01:25.50` or `MM:SS.ss`). NEVER suggest absolute elapsed timestamps (e.g. `17:25:27` or `62727.0`)!
"""


def get_handshake_verifier_user_prompt(
    qa_pair: dict,
    retriever_response: dict,
    video_clips_summary: str,
) -> str:
    """Step 3: User prompt for verifier evaluation (no super ledger)."""
    from .common import format_qa_pair_markdown

    # Format caption excerpts
    caption_lines = []
    excerpts = retriever_response.get("caption_excerpts", [])
    if excerpts:
        caption_lines.append("## Retrieved Caption Excerpts")
        for i, exc in enumerate(excerpts, 1):
            vid = exc.get("video_id", "?")
            start = exc.get("start_time", "?")
            end = exc.get("end_time", "?")
            caption_lines.append(f"### Excerpt {i}: {vid} [{start} – {end}]")
            caption_lines.append(exc.get("caption_text", "_No caption text._"))
            meta = exc.get("segment_metadata", "")
            if meta:
                caption_lines.append(f"_Metadata: {meta}_")
            caption_lines.append("")

    additional = retriever_response.get("additional_context")
    if additional:
        caption_lines.append(f"## Additional Context from Retriever")
        caption_lines.append(additional)
        caption_lines.append("")

    # Format clip fulfillment info
    clip_lines = []
    fulfilled = retriever_response.get("fulfilled_clips", [])
    if fulfilled:
        clip_lines.append("## Clip Availability")
        for fc in fulfilled:
            status = "✅ Available" if fc.get("available") else "❌ Not Available"
            clip_lines.append(
                f"- {fc.get('video_id', '?')} [{fc.get('start_time', '?')} – {fc.get('end_time', '?')}] "
                f"— {status}: {fc.get('relevance_note', '')}"
            )

    return f"""\
QA PAIR TO VERIFY:
{format_qa_pair_markdown(qa_pair)}

RETRIEVED CONTEXT (from Super Ledger):
{chr(10).join(caption_lines) if caption_lines else '_No captions retrieved._'}

{chr(10).join(clip_lines) if clip_lines else ''}

VIDEO CLIPS PROVIDED (File Context):
{video_clips_summary}

Score this QA pair following the rubric in your instructions."""
