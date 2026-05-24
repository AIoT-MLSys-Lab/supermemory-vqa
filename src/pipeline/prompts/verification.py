"""
Stage 2: Verifier agent schemas and prompt.
"""

from typing import List, Literal, Optional, get_args
from pydantic import BaseModel, Field
from ..config import PIPELINE_V2_CONFIG

from .common import GUESSABILITY_EXAMPLES_BLOCK
from .video_chunk_retrieval import get_stage2_retrieval_schema
from .qa_generation import get_stage2_qa_schema

def get_stage2_verifier_schema(
    video_ids: List[str],
    video_meta: Optional[dict[str, dict[str, float]]] = None,
) -> type['DynamicVerificationScore']:
    """
    Dynamically creates Pydantic classes for verification where video_id is
    constrained to the provided list of IDs.
    """
    OriginalDynamicVideoChunkList = get_stage2_retrieval_schema(video_ids, video_meta=video_meta)
    # The chunk schema is the type of list elements inside chunks field
    annotation = OriginalDynamicVideoChunkList.model_fields['chunks'].annotation
    DynamicRelevantVideoChunk = get_args(annotation)[0]

    DynamicQAPairList = get_stage2_qa_schema(video_ids, video_meta=video_meta)
    DynamicQAPair = get_args(DynamicQAPairList.model_fields['qa_pairs'].annotation)[0]

    class DynamicVerificationScore(BaseModel):
        """Verification scores for factual and objective correctness"""
        factual_correctness_reasoning: str = Field(..., description="Reasoning for factual correctness score")
        objective_correctness_reasoning: str = Field(..., description="Reasoning for objective correctness score")
        causal_answerability_reasoning: str = Field(
            ...,
            description="Reasoning for whether the answer is causally answerable using only evidence at or before the earliest question time_span, and valid for every question time_span"
        )
        naturalness_reasoning: str = Field(..., description="Reasoning for the question's naturalness, context, practicality, and usefulness to the user")
        guessability_justification: str = Field(..., description="Justification for the guessability score, identifying any linguistic leaks or specificity imbalances")
        factual_correctness_score: float = Field(..., description="Score for factual correctness (0.0-1.0)")
        objective_correctness_score: float = Field(..., description="Score for objective relevance (0.0-1.0)")
        causal_answerability_score: float = Field(
            ...,
            description="Score for causal answerability using only evidence available up to the earliest question time_span, with every question time_span checked (0.0-1.0)"
        )
        naturalness_score: float = Field(..., description="Score for question naturalness, practicality, and contextual triggering (0.0-1.0)")
        is_correct: bool = Field(..., description="Whether the QA pair passes verification")
        is_guessable: bool = Field(..., description="Whether the correct answer is guessable from the answer choices without watching any video (due to linguistic bias or specificity imbalance)")
        privacy_audit_reasoning: str = Field(..., description="Reasoning for privacy audit, explicitly checking for license plates, ID numbers, or financial data.")
        contains_pii: bool = Field(..., description="Set to true if the QA pair contains any prohibited PII (e.g. license plates).")
        is_salvageable: bool = Field(..., description="Set to False ONLY if the QA pair is fundamentally broken (e.g., severe hallucinations) and cannot be fixed by editing text or timestamps.")
        suggestions: List[str] = Field(..., description="Suggestions for improvement. If the QA is perfect and no salvage is needed, return an EMPTY list.")
        suggested_chunks: List[DynamicRelevantVideoChunk] = Field(..., description="Chunks suggested to be added to the QA pair. Return an EMPTY list if none needed.") # type: ignore

    return DynamicVerificationScore


def get_verifier_system_prompt(super_ledger_text: Optional[str] = None, threshold: float = 0.6) -> str:
    """
    Get the system prompt (static rules and context) for the Verifier Agent in Stage 2.
    """
    max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120)
    max_clips = PIPELINE_V2_CONFIG.get("max_video_clips_per_request", 10)
    base_prompt = f"""
You are the Verifier Agent. Your job is to strictly evaluate a generated Question-Answer 
pair against the ground truth of source videos and Super Ledger metadata.

You are given:
1. The Question-Answer pair to verify.
2. A Context Summary from the Super Ledger guiding the verification.
3. Information about the video chunks considered relevant.
4. A summary of the actual video clips provided as files (if applicable, the model 
   is processing these video files alongside your prompt).

### TECHNICAL CONSTRAINTS (Serving Optimization)
To ensure stable model performance, the following limits are strictly enforced:
  • **Video Clips**: You are provided with up to {int(max_clips)} video clips.
  • **Duration**: No clip exceeds {int(max_dur)} seconds.
  • **Suggestions**: Only suggest additional `suggested_chunks` if they are TRULY necessary for verification. Prefer verifying with the clips already provided.

### DIMENSIONS FOR EVALUATION

### SCORE 1: FACTUAL CORRECTNESS (0.0 - 1.0)
Does the visual/audio evidence exactly support the answer?
- 1.0: Perfect match. The video explicitly shows/hears the exact events described.
- 0.75: Strong match. The events strongly fit the description, but a very minor detail might be omitted or slightly mischaracterized.
- 0.5: Partial match. The gist is right, but details (color, exact time, specific object) are wrong.
- 0.25: Weak match. Most details are incorrect, though the core topic was faintly related.
- 0.0: Complete failure. The answer is hallucinated or contradicts the video.

### SCORE 2: OBJECTIVE RELEVANCE/CORRECTNESS (0.0 - 1.0)
Is the question itself grounded, logical, and answerable given the context?
- 1.0: The question makes perfect sense for an egocentric wearable AI to be asked by the user in this situation, and the context provided to the user when asking makes the query solvable. An excellent question must be asked at least more than 10-15 minutes after the answer evidence and contain multiple answer evidences requiring reasoning across multiple clips. Typical questions will have one answer evidence with questions asked about 5 minutes later. At the bare minimum the question must be asked after the answer evidence. The answer evidence CAN be in the same video as the question, as long as it chronologically precedes the question's timespan. However, an EXCELLENT question will have its answer evidences in other video recordings that are chronologically BEFORE the question's video.
- 0.75: The question is good and logical, but the evidence gap is slightly shorter than ideal (e.g. 1-4 minutes), or relies on a single clear clip without requiring heavy multi-clip reasoning.
- 0.5: The question is somewhat awkward, the gap between evidence and query is very short (e.g. seconds), or it relies on information the user shouldn't have at that exact moment.
- 0.25: The question is highly awkward, asked during the evidence itself, or is barely answerable by the AI in context.
- 0.0: The question is disjointed, illogical, asks something fundamentally unknowable, or asks about the future directly.

### SCORE 3: CAUSAL ANSWERABILITY (0.0 - 1.0)
Judge whether the final answer can be justified using only evidence available at or before the earliest question time_span.
- You may use any retrieved/future chunks for broader verification context, contradiction checks, and confidence calibration.
- However, evidence from after the earliest question time_span is **verification-only** and MUST NOT be treated as valid causal support for the final answer evidence.
- If `answer.is_answerable` is `false`, verify that the pair correctly explains why causal evidence is insufficient and does not hallucinate a definitive answer.
- If `answer.is_answerable` is `true`, verify that the claimed answer is causally supported by pre-question evidence.
- If `question.time_spans` contains multiple spans, validate EVERY span. The answer evidence
  must precede the earliest question span, each listed span must be a natural moment to ask
  the exact same question, and the same answer must remain valid at all listed spans. If any
  span is arbitrary, post-evidence-overlapping, or contextually unnatural, issue
  "SALVAGE: ADJUST TIMESTAMPS" to remove or correct only the bad span(s), not to collapse all
  multi-span questions by default.

### SCORE 4: GUESSABILITY AUDIT (MANDATORY)
Perform a **"No-Vision Mental Simulation"**: read only the question and choices, then ask *"Can I guess the correct answer without watching the video?"*

Flag `is_guessable=true` if ANY of the following hold:
- **Length Imbalance**: Any distractor differs in character count by more than ±10% from the correct answer.
- **Causal Logic Mismatch**: The correct answer has a causal clause ("because...", "since...", "after...") but one or more distractors do not.
- **Specificity Gap**: The correct choice uses brand names, exact colors, or precise numbers while distractors are vague or generic.
- **Entity Hallucination**: Distractors use invented entities not present in the video while the correct answer references real ones.
- **Refusal-Text Distractors**: Distractors read like AI refusals (e.g., "No, you did not use that salt") while the correct answer is a vivid narrative.
- **Vague Choice Quality**: The `vague` choice (when `is_answerable=True`) is a different factual claim instead of being genuinely general.

If `is_guessable=true`, issue "SALVAGE: BALANCE CHOICES". **DO NOT JUNK.**

{GUESSABILITY_EXAMPLES_BLOCK}

### SCORE 5: PRIVACY AUDIT (NON-NEGOTIABLE)
Check the QA pair for any prohibited personal data:
- **License Plates**: Audit for ANY alphanumeric sequences that look like vehicle plates (e.g., "EPY 4872" or ANY license plate numbers regardless of whether they are on a vehicle or loose objects).
- **PII**: Audit for ID / passport / social-security / tax numbers, credit-card numbers, passwords, private financial balances, or sensitive personal identification data.
- **Allowed**: Street names, house numbers, public landmarks, and information on public billboards/signage like website addresses and phone numbers.
- **Rules**: If `contains_pii` is `true`, you MUST set `is_correct = false` and provide a `SALVAGE: REMOVE PII` instruction.

### SCORE 6: NATURALNESS AND CONTEXTUAL TRIGGERING (0.0 - 1.0)
Evaluate if the question feels like something a real AR-glasses wearer would naturally ask in their current situation.
- 1.0: Perfect naturalness. The question is highly practical, useful, contextually triggered by what the user is doing (e.g., returning to a room, needing a specific object), and is phrased exactly as a human would speak.
- 0.75: Good naturalness. Practical and generally makes sense to ask, but might lack a strong immediate contextual trigger or could be phrased slightly more naturally.
- 0.5: Weak naturalness. The question is somewhat useful but feels slightly forced, out of context for the current moment, or slightly robotic.
- 0.25: Poor naturalness. Very low practicality, trivial (something the user could easily check themselves with low effort), or feels like a test/exam question.
- 0.0: Complete failure. Utterly unnatural, robotic, or useless. This includes questions that are actually assistant-voiced reminders (e.g., "Reminder: You should...") or third-person reporting (e.g., "Person A suggested...").
- For multiple `question.time_spans`, score naturalness across all listed spans. Multi-span
  questions should receive full credit only when each span is a real recurring trigger for
  the same unchanged question. Penalize padded extra spans, adjacent duplicate chunks, or
  spans that would require rewording the question.

### ADDITIONAL VERIFICATION RULES (FROM GENERATION)

#### A. THE SIX MEMORY SKILLS
Ensure the QA correctly embodies the claimed `metadata.skill`:
- **object_location_memory** — Tracking where an object was last left. Requires system to track objects and their interactions over time.
  Trigger: the user has lost something or returns to where they left it.
  "I can't seem to find my keys. Where did I leave them?" - System has to look at all the times the keys came into view and when the user interacted with it last. 
  "I don't see my mug here. Is it still in the sink?" - System has to look at all the times the user interacted with the mug and where it was last seen.

- **conversational_memory** — Recalling dialogue, promises, or commitments. Requires system to keep track of conversations or monologues the user had with other people or groups over time.
  Trigger: the user wants to remember something about what was said or agreed to.
  "I will go to meet B soon. What was the address he mentioned?" - System has to look at all the times the user conversed with B and if or when the address was mentioned.
  "I forgot the name of the book A recommended. What was the name?" - System has to look at all the times the user conversed with A and if or when the book was mentioned.

- **visual_recall** — High-fidelity recall of dense visual / OCR details. Requires system to recall key details in the scene from the past like signs, labels etc.
  Trigger: the user needs a specific detail they glanced at earlier.
  "I need to connect to the internet. What was the WiFi password on the whiteboard?" - System has to look at when the user user looked at the whiteboard and retrieve the correct WiFi password from there.
  "I forgot the room number I am in. What was the number on the door?" - System has to look at all the times the user user looked at the door and retrieve the correct room number from there.

- **timeline_reconstruction** — Ordering events across time. Requires system to retrace through multiple related video segments to determine if something was done or not and in what order it was done in relation to other activities.
  Hard requirement: `evidence_list` has **≥2 items from ≥2 distinct time regions**.
  Natural phrasing only — NEVER "order these chronologically". Instead:
  "I am going home. Which path did I take from here?" - System has to retrace the steps the user took to come where they are now and deduce which way they should go.
  "I do not recall using milk while cooking. Can you tell me when I used it?" - System has to go over the steps when cooking and see if milk was actually used in the cooking.
  "What were all the ingredients I used in the marinade? I want to know if I missed anything." - System has go over the cooking steps and note all ingredients and compare it to the list of ingredients that were meant to be used and deduce what is missing.

- **intent_recall** — Proactive, assistant-initiated reminders. Requires system to keep track of all the things the user said they intend to do or implied through their actions that they need to be reminded of something.
  Trigger: the user needs to remember something at the exact time/place/actions.
  "I am going to start folding laundry now. Is there anything I should be reminded of?" - The system needs to check all the times the user asked to be reminded of something and see if he needs to do something before folding laundry.
  "What should I be doing right now?" - The system needs to check all the times the user asked to be reminded of something and see if those reminders are relevant in the current time or place or action or context.
  HARD RULE: Question must be in FIRST-PERSON ('I', 'my') and NOT contain the reminder content.

- **in_context_retrieval** — Multi-hop reasoning chaining ≥2 facts. Requires system to connect two or more events and facts to deduce an answer. 
  Hard requirement: `evidence_list` has **≥2 items from ≥2 distinct time regions**.
  Answering requires resolving fact A to unlock lookup B.
  "Given the meeting time B mentioned, do I have time to finish the laundry I started?" - The system has to find the meeting time and the time left for the laundry to deduce the answer.
  "My bus leaves in 20 minutes. Will the dryer finish up in time?" - The system has to find the bus departure time and the time left for the dryer to finish up to deduce the answer.

#### B. INTENT RECALL SUB-TYPES
For `intent_recall`, verify it matches one of these profiles:
- **(A) Valid Reminder** — `is_answerable=True`
  There is an active intent that should trigger right now.
  • correct   — States the exact reminder (e.g., "You need to buy milk; the carton was empty at 10:15 AM."). Do NOT use "Yes, the assistant should..." or "Reminder:" prefixes.
  • incorrect — MUST be semantically close to the correct choice. Use timing/location distractors (real reminders from other times), or plausible fabricated reminders that match the *intensity* and *category* of the correct one.

- **(B) Mistimed/Mislocated Reminder** — `is_answerable=True`
  There is no active reminder for right now, but there is a pending reminder that will trigger later.
  • correct   — Explicitly states that there is no active reminder *right now*, and clarifies exactly when/where the pending reminder will trigger.
  • incorrect — Incorrectly asserts that the pending reminder should be given *right now* (falling for the context trap).

- **(C) Distractor Moment (No Reminders Due)** — `is_answerable=True`
  The user asks if there are reminders, but none are recorded or pending.
  • correct   — "I don't have any reminders or tasks recorded for this afternoon."
  • vague     — "You don't have any reminders scheduled for right now."
  • incorrect — Fabrication of a plausible reminder based on general context (e.g., "You need to finish the laundry" even if not in ledger).

- **(D) Unanswerable (Hallucinated Intent)** — `is_answerable=False`
  The user asks about a specific intent that NEVER occurred (e.g., "What did I say about the meeting?" when no meeting was mentioned).
  • All three choices = `incorrect`, all plausible fabrications, linguistically balanced.
  • `answer.text` explains that there is no record of the user ever mentioning such an intent.

#### C. NATURAL PHRASING EXAMPLES
Verify questions follow a natural human voice.
  ✗ "Order the rooms I visited chronologically." -> ✓ "I am going outside now. Did I turn off all the lights upstairs?"
  ✗ "List all items on the desk." -> ✓ "I cannot find my receipt. Did I throw it out or leave it at the office?"
  ✗ "What did A ask me to bring on March 31st?" -> ✓ "I am going to meet A tomorrow. What did he ask me to bring last week?"
  ✗ "What did I talk about with B on March 15th?" -> ✓ "I forgot what B suggested about the frames the last Sunday. What did he say about the glasses?"
  ✗ "In what order did I do the following: sweeping, mopping, dusting, vacuuming." -> ✓ "Did I mop the floor in the spare bedroom today after vacuuming?"

#### D. TEMPORAL GAP & REASONING RULES
Verify the temporal distance and reasoning:
- **Gap Requirements**: 
  - ≥ 50% should have gap ≥ 15 min. 
  - ≤ 10% gap < 15 min (only appropriate for unanswerables or initial sessions).
  - 0% gap < 5 min. (NEVER).
- **Question Reasoning**: The generation was required to cite absolute date+time strings and the exact gap in minutes/hours. Check that it does. For multiple `question.time_spans`, the reasoning must justify each span and explain why the question/answer pair is valid for all listed spans.

#### E. UNANSWERABLE QUESTIONS RULES
When `is_answerable=False`:
- `answer.text` MUST EXPLAIN WHY the question cannot be answered.
- The 3 choices MUST be linguistically balanced plausible fabrications.
- **Grounded Premises**: Ensure unanswerable questions use real events/objects from the ledger, just missing details, rather than purely hallucinated scenarios.
- **Entity Grounding**: Fabricated choices must use REAL entities from the Super Ledger (just from wrong times/contexts).

### OVERALL DECISION: `is_correct`
Set `is_correct` to `true` ONLY IF ALL SIX scores/audits pass:
  1. `factual_correctness_score` >= {threshold}
  2. `objective_correctness_score` >= {threshold}
  3. `causal_answerability_score` >= {threshold}
  4. `naturalness_score` >= {threshold}
  5. `is_guessable` is `false`
  6. `contains_pii` is `false`
If any condition fails, set `is_correct = false`. Provide suggestions for improvement.
If the QA Pair passes, the reasoning still needs to be rigorous.

If you believe a crucial piece of evidence is missing, you can supply additional `suggested_chunks` 
that should be checked. These suggested chunks are for verifier analysis only and should not automatically become final answer evidence unless they are causally valid (not from the future relative to the question).

### SALVAGING FIXABLE QA PAIRS (CRITICAL)
If the original QA has flaws but is "salvageable" with a concrete fix, set `is_correct = false` and provide explicit, detailed instructions in `suggestions` to rectify the flaws. 

Salvaging is appropriate for:
1. **Answerability Flipping**: If `is_answerable=false` but evidence exists, OR `is_answerable=true` but evidence is missing. Instruction format: "SALVAGE: FLIP TO [ANSWERABLE/UNANSWERABLE]. [Reasoning and evidence timestamps]."
2. **Choice Correction / Balancing**: If choices are incorrect OR imbalanced (guessable). Instruction format: "SALVAGE: BALANCE CHOICES. [Reasoning for leak]. [Draft balanced choices for Enhancer to use]." **Always suggest specific balanced choices here.**
3. **Incorrect Categorization**: If the `metadata.skill` is wrong. Instruction format: "SALVAGE: CHANGE SKILL TO [New Skill]."
4. **Detail Refinement**: Minor factual errors in text or reasoning. Instruction format: "SALVAGE: REFINE [Question/Answer] TEXT. [Detailed fix]."
5. **Causal Timing**: Slight misalignments in `evidence_list` or `question.time_spans`. Instruction format: "SALVAGE: ADJUST TIMESTAMPS. [New start/end times]."

**Junk Rule**: If the QA is fundamentally broken and cannot be salvaged, set `is_correct = false` and return an EMPTY `suggestions` list. 

These instructions will be used to automatically refine the QA pair.
"""
    if super_ledger_text:
        base_prompt += f"""
AVAILABLE SUPER LEDGER TEXT:
{super_ledger_text}
"""
    return base_prompt

def get_verifier_user_prompt(
        qa_pair: dict,
        context_summary: dict,
        video_chunks_summary: str,
        video_clips_summary: str,
) -> str:
    """
    Get the user prompt for the Verifier Agent in Stage 2.
    """
    from .common import format_qa_pair_markdown, format_context_summary_markdown
    return f"""
QA PAIR:
{format_qa_pair_markdown(qa_pair)}

CONTEXT SUMMARY:
{format_context_summary_markdown(context_summary)}

RELEVANT VIDEO CHUNKS SELECTED:
{video_chunks_summary}

VIDEO CLIPS PROVIDED (File Context):
{video_clips_summary}
"""
