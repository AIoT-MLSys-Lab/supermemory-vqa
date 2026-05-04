"""
Common Pydantic schemas shared across pipeline_v2 stages.

Base classes defined here are inherited by the dynamic schema generators
in qa_generation.py and enhancement.py.  Adding a field to a base class
automatically propagates it to every downstream agent.
"""

from typing import List, Literal, Generic, TypeVar, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── Shared Literal types ──────────────────────────────────────────────
MODALITIES_TYPE = Literal["Video", "Audio", "Gaze", "Trajectory", "Depth", "OCR"]
SKILL_TYPE = Literal[
    "object_location_memory",
    "conversational_memory",
    "visual_recall",
    "timeline_reconstruction",
    "intent_recall",
    "in_context_retrieval",
]


class TimeSpan(BaseModel):
    """Start and end times for a video segment or event"""

    start_time: str = Field(..., description="Start time in MM:SS format within the video")
    end_time: str = Field(
        ...,
        description="End time in MM:SS format within the video, must be strictly greater than start_time",
    )

    @model_validator(mode="after")
    def validate_times(self) -> "TimeSpan":
        def to_sec(ts: str) -> float:
            parts = ts.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                return float(ts)
            except (ValueError, IndexError):
                return 0.0

        if to_sec(self.start_time) >= to_sec(self.end_time):
            raise ValueError("start_time must be strictly less than end_time")
        
        if to_sec(self.end_time) - to_sec(self.start_time) >= 240:
            raise ValueError("Time span duration must be less than 240 seconds")
        
        return self


class BoundingBox(BaseModel):
    """2D Bounding box for visual elements. Fields are normalized to 0-1000."""

    label: str = Field(
        ...,
        description="A short, descriptive label for the object (e.g., 'red car', 'person A')",
    )
    ymin: int = Field(..., description="The top edge of the bounding box (0 to 1000)")
    xmin: int = Field(..., description="The left edge of the bounding box (0 to 1000)")
    ymax: int = Field(..., description="The bottom edge of the bounding box (0 to 1000)")
    xmax: int = Field(..., description="The right edge of the bounding box (0 to 1000)")
    time_offset: str = Field(
        ...,
        description="The specific time (MM:SS) within the video chunk when this object appears",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "label": "Coffee mug",
                "ymin": 450,
                "xmin": 300,
                "ymax": 550,
                "xmax": 400,
                "time_offset": "01:23",
            }
        }
    )


# ── Base schema classes ───────────────────────────────────────────────
# Downstream dynamic schemas (qa_generation, enhancement) inherit from
# these so that any new field automatically propagates everywhere.
# We use Generic typing to allow subclasses to specify the dynamic
# video_id Literal type AND to preserve the strict field ordering requested.

VideoIdT = TypeVar("VideoIdT")
EvT = TypeVar("EvT")
ChoiceT = TypeVar("ChoiceT")


class BaseQuestionTimeSpan(TimeSpan, Generic[VideoIdT]):
    """Time span mapping specifically for a question's location, requiring
    explicit generic Video IDs."""

    video_id: VideoIdT = Field(
        ..., description="The exact video ID from the ledger where this timespan occurs."
    )


class BaseAnswerEvidence(BaseModel, Generic[VideoIdT]):
    """Base evidence item."""

    reason: str = Field(
        ...,
        description=(
            "Justification for this evidence. Must (1) quote or closely paraphrase the "
            "specific ledger fragment (field: activities/objects/people/visible_text/audio_transcript/environment) "
            "supporting the answer, (2) explain HOW that fragment contributes to the answer "
            "rather than merely restating it, and (3) be independently verifiable from the ledger. "
            "Example good reason: 'At 12:03 in vid_a, audio_transcript captured \"I will leave the keys "
            "by the toaster\" — the final stated location of the keys before the question.'"
        ),
    )
    room: str = Field(
        ...,
        description=(
            "Room or location where this evidence occurs, as stated in the ledger's "
            "environment field. Use the exact phrasing present in the ledger; do not "
            "invent or generalize."
        ),
    )
    time_span: TimeSpan = Field(..., description="Time span containing answer evidence")
    video_id: VideoIdT = Field(
        ..., description="Video ID from the ledger where evidence is found"
    )
    modalities: List[MODALITIES_TYPE] = Field(
        ...,
        description=(
            "Sensor modalities that were required to capture THIS specific evidence originally. "
            "Include only what is genuinely needed. Semantics: Video=visual environment/actions; "
            "Audio=speech/ambient sound; OCR=legible text on signs/labels/screens/documents; "
            "Gaze=what the user is looking at, reading intently vs. skimming, medium being read; "
            "Trajectory=path taken, room sequence, navigation; Depth=spatial layout, object distance/size."
        ),
    )


class BaseQuestion(BaseModel, Generic[VideoIdT]):
    """Base question schema."""

    question_reasoning: str = Field(
        ...,
        description=(
            "Justification of the question's naturalness AND its temporal placement. Must include: "
            "(1) the natural trigger that would prompt this question at the stated moment — returning "
            "to a room, seeing a related object, continuing a conversation topic, time-of-day routine, "
            "encountering the relevant person, etc.; (2) the temporal gap in minutes or hours between "
            "question and evidence; (3) the absolute dates/times cited from the ledger headers for "
            "BOTH the question moment and the evidence moment; (4) why it is plausible the user would "
            "ask NOW rather than earlier. Robotic/test-like motivations ('to test ordering ability') "
            "are unacceptable."
        ),
    )
    text: str = Field(
        ...,
        description=(
            "For all skills, a natural first-person question ('I', 'my') the user would genuinely ask — "
            "curiosity-driven, forgetfulness-driven, or context-triggered. "
            "HARD REQUIREMENT: Always use first-person ('I', 'my'). Even for intent_recall, "
            "this MUST be the user's trigger question, NOT an assistant's reminder. "
            "NOT exam-like ('order these events', 'list all items')."
        ),
    )
    room: str = Field(
        ...,
        description=(
            "The user's room/location at the question moment (or where the intent_recall reminder fires), "
            "using the exact phrasing from the ledger's environment field for the corresponding time_span. "
            "For intent_recall place-triggered reminders, this is the location whose arrival activates "
            "the reminder."
        ),
    )
    time_spans: List[BaseQuestionTimeSpan[VideoIdT]] = Field(  # type: ignore
        ...,
        description=(
            "One or more video-local MM:SS intervals where the question is naturally asked "
            "(or where the intent_recall reminder fires). Use multiple intervals when the question "
            "would recur in similar contexts (e.g., every time the user enters the kitchen). "
            "Hard rules: (a) each interval's video_id MUST be present in the ledger; "
            "(b) the EARLIEST start_time across ALL intervals must be strictly chronologically "
            "AFTER the LATEST end_time of ALL evidence time_spans, measured on the global ledger "
            "timeline (cross-video gaps count real-world time between sessions); (c) no interval "
            "may overlap any evidence interval; (d) bounds must match exactly the MM:SS ranges "
            "printed in the ledger."
        ),
    )
    video_id: VideoIdT = Field(
        ...,
        description=(
            "Video ID for the primary context in which the question is asked or the reminder fires. "
            "Must be an exact ID present in the ledger and must match the video_id of the first "
            "(or sole) time_spans entry. Never invent."
        ),
    )
    modalities: List[MODALITIES_TYPE] = Field(
        ...,
        description=(
            "Modalities the AR assistant needs AT THE QUESTION MOMENT to interpret the user's "
            "current context (not the modalities needed to answer — those go on each evidence item). "
            "Include only what is genuinely needed. Semantics: Video=visual environment/actions; "
            "Audio=speech/ambient sound; OCR=legible text on signs/labels/screens/documents; "
            "Gaze=what the user is looking at, reading intently vs. skimming, medium being read; "
            "Trajectory=path taken, room sequence, navigation; Depth=spatial layout, object distance/size."
        ),
    )

    @model_validator(mode="after")
    def _question_video_id_matches_first_span(self) -> "BaseQuestion":
        if self.time_spans:
            first_vid = self.time_spans[0].video_id
            if first_vid != self.video_id:
                raise ValueError(
                    f"question.video_id ({self.video_id!r}) must match the first "
                    f"time_spans entry's video_id ({first_vid!r})."
                )
        return self


class BaseAnswerChoice(BaseModel):
    """Single answer choice — field order: explanation, choice_type, text."""

    explanation: str = Field(
        ...,
        description=(
            "Explanation of why this choice earns its choice_type, citing the relevant "
            "evidence or its absence. For 'vague', identify the specific missing specificity. "
            "For 'incorrect', identify the contradiction with the evidence or flag it as a "
            "plausible fabrication (unanswerable case)."
        ),
    )
    choice_type: Literal["correct", "vague", "incorrect"] = Field(
        ...,
        description=(
            "'correct' = precise, complete answer fully supported by evidence (matches answer.text). "
            "Only valid when answer.is_answerable=True. "
            "'vague' = technically true but too general/ambiguous to be actionable. "
            "'incorrect' = contradicts the evidence or, for unanswerable questions, is a plausible "
            "fabrication. For intent_recall: 'correct' provides the direct reminder (or states 'no reminders due'); "
            "'vague' is overly general; 'incorrect' provides a mistimed/mislocated/misdirected real intent or a fabrication."
        ),
    )
    text: str = Field(
        ...,
        description=(
            "The user-facing answer text. For choice_type='correct', this must match "
            "DynamicAnswer.text. Never reveal meta-information such as 'this is the vague "
            "option' or references to evidence times."
        ),
    )


class BaseAnswer(BaseModel, Generic[EvT, ChoiceT]):
    """Base answer — field order: evidence_list, is_answerable, answer_choices, text."""

    evidence_list: List[EvT] = Field(
        ...,
        description=(
            "Chronologically ordered evidence supporting this answer. "
            "When is_answerable=True: MUST contain at least 1 item, and for skills "
            "'timeline_reconstruction' and 'in_context_retrieval' MUST contain at least 2 items "
            "drawn from at least 2 distinct time regions. "
            "When is_answerable=False: MAY be empty; otherwise should point to the nearest "
            "related context a naive system might mistake for an answer."
        ),
    )
    is_answerable: bool = Field(
        ...,
        description=(
            "True iff the ledger contains sufficient unambiguous evidence to answer. "
            "Set to False when (a) required information is absent from the ledger, "
            "(b) the question refers to an intent/event that never occurred (hallucination probe), "
            "or (c) the evidence is fundamentally ambiguous. Approximately 40% of QA pairs per batch "
            "should be is_answerable=False. When False: answer.text explains why; all 3 answer_choices "
            "have choice_type='incorrect'. MUST be set on the answer object — NEVER on the question object."
        ),
    )
    answer_choices: List[ChoiceT] = Field(
        ...,
        description=(
            "Exactly 3 answer choices. For is_answerable=True: exactly one 'correct' (matching answer.text), "
            "one 'vague' (technically not wrong but too general to be useful), and one 'incorrect' "
            "(contradicts evidence but plausible as a distractor or too specific in a way that is unsubstantiated "
            "by evidence). For is_answerable=False: all three are 'incorrect' — plausible-sounding fabrications "
            "that MUST be linguistically balanced (similar length, specificity, and syntax) so the question's "
            "unanswerability cannot be deduced from the choices alone."
        ),
    )
    text: str = Field(
        ...,
        description=(
            "Precise, detailed answer to the user's question. For is_answerable=True, "
            "this is the correct, complete answer and MUST match the text of the "
            "answer_choices item with choice_type='correct'."
            "For is_answerable=False, this field MUST explain WHY the question cannot be answered."
        ),
    )

    @model_validator(mode="after")
    def _validate_evidence_and_choices(self) -> "BaseAnswer":
        # Evidence-list count vs. is_answerable
        ev_count = len(self.evidence_list)
        if self.is_answerable and ev_count < 1:
            raise ValueError(
                "answer.evidence_list must contain at least 1 item when is_answerable=True."
            )

        # Choice composition vs. is_answerable
        types = [c.choice_type for c in self.answer_choices]
        if self.is_answerable:
            if (
                types.count("correct") != 1
                or types.count("vague") != 1
                or types.count("incorrect") != 1
            ):
                raise ValueError(
                    "When is_answerable=True, answer_choices must contain exactly one "
                    "'correct', one 'vague', and one 'incorrect'."
                )
            # 'correct' choice text must match answer.text
            correct_text = next(
                c.text for c in self.answer_choices if c.choice_type == "correct"
            )
            if correct_text != self.text:
                raise ValueError(
                    "When is_answerable=True, answer.text must match the 'correct' "
                    "answer_choice text byte-for-byte."
                )
        else:
            if any(t != "incorrect" for t in types):
                raise ValueError(
                    "When is_answerable=False, all 3 answer_choices must have choice_type='incorrect'."
                )
        return self


class BaseQAMetadata(BaseModel, Generic[VideoIdT]):
    """Base metadata — field order: skill_reasoning, skill, primary_video_id."""

    skill_reasoning: str = Field(
        ...,
        description=(
            "Reasoning for choosing this specific skill for the given QA pair. "
            "Explain how the question and evidence map to the skill's definition."
        ),
    )
    skill: SKILL_TYPE = Field(
        ...,
        description=(
            "The primary memory skill tested. Exactly one value from the enum. Use: "
            "object_location_memory (tracking where something was left); conversational_memory "
            "(recalling what was said/promised); visual_recall (dense visual or OCR details); "
            "timeline_reconstruction (ordering events across time — MUST have ≥2 evidence items); "
            "intent_recall (assistant-initiated proactive reminder); in_context_retrieval "
            "(multi-hop reasoning chaining ≥2 facts — MUST have ≥2 evidence items)."
        ),
    )
    primary_video_id: VideoIdT = Field(
        ...,
        description="Video ID where the question is asked for the first time. Must be an exact ID from the ledger.",
    )


# ──────────────────────────────────────────────────────────────────────
# Single source of truth for modality semantics — referenced by all agents.
# ──────────────────────────────────────────────────────────────────────
MODALITY_SEMANTICS_BLOCK = """\
### MODALITY SEMANTICS (apply everywhere modalities are selected)
Select ONLY modalities that are genuinely required. Do not include modalities by default.
  • Video       — visual state of environment, objects, actions
  • Audio       — spoken content, conversations, ambient sound
  • OCR         — legible text on signs, labels, screens, documents
  • Gaze        — what the user is looking at; reading intently vs. skimming; medium being read
  • Trajectory  — path taken, room sequence, navigation, movement
  • Depth       — spatial layout, object distance/size, scene geometry

Contextual rules:
  • `question.modalities` = what the assistant needs AT THE QUESTION MOMENT to interpret the
    user's present context (NOT what is needed to answer — that lives on each evidence item).
  • `evidence.modalities` = what was originally needed to capture THAT specific piece of evidence.
"""

# ──────────────────────────────────────────────────────────────────────
# Single source of truth for guessability examples — referenced by all agents.
# ──────────────────────────────────────────────────────────────────────
GUESSABILITY_EXAMPLES_BLOCK = """\
**Examples of Linguistic Balancing (Good/Bad Choices by Skill):**

*1. object_location_memory*
- **Question**: "I want to make coffee. Where did I leave my blue mug?"
- **Correct**: "You left the blue mug on the kitchen island, right next to the toaster."
- ❌ **Bad Incorrect** (Generic): "You left it in the living room." (Model easily spots this lacks the specificity of the correct answer).
- ✅ **Good Incorrect** (Matched Specificity): "You left the blue mug on the coffee table in the living room, right next to the remote control."

*2. conversational_memory*
- **Question**: "I want to work on our project. What did B say about the project deadline?"
- **Correct**: "He said the deadline was moved to Friday because the client requested extra features."
- ❌ **Bad Incorrect** (Missing causal logic): "He said the deadline was moved to Monday." (Model will pick the correct answer because it has richer logical texture).
- ✅ **Good Incorrect** (Logic Mirrored): "He said the deadline was moved to Monday because the engineering team needed more time for testing."

*3. visual_recall*
- **Question**: "I want to buy a scooter. What was the brand of the orange scooter I passed?"
- **Correct**: "The brand printed on the side of the scooter was Spin."
- ❌ **Bad Incorrect** (Vague/Length mismatch): "Lime."
- ✅ **Good Incorrect** (Style Mirrored): "The brand printed on the side of the scooter was Lime."

*4. timeline_reconstruction*
- **Question**: "I want to make sure I got everything right. In what order did I add the spices to the pan?"
- **Correct**: "You added cumin seeds first, followed by ground black pepper, and finally bay leaves."
- ❌ **Bad Incorrect** (Too short/robotic): "Pepper, bay leaves, cumin."
- ✅ **Good Incorrect** (Style Mirrored): "You added ground black pepper first, followed by bay leaves, and finally cumin seeds."

*5. intent_recall*
- **Question**: "I am near the grocery store. Was there anything I intended to pick up?"
- **Correct**: "You need to buy whole milk; you noticed the carton was empty this morning."
- ❌ **Bad Incorrect** (Generic/Vague): "You need to buy some groceries."
- ✅ **Good Incorrect** (Matched Style/Context): "You need to buy almond milk; you noticed the carton was empty this morning."

*6. in_context_retrieval*
- **Question**: "Given the meeting time B mentioned, do I have time to finish the laundry I started?"
- **Correct**: "Yes, the meeting is at 3:00 PM, and the laundry will finish at 2:15 PM, leaving you 45 minutes."
- ❌ **Bad Incorrect** (Missing logic steps): "Yes, you have plenty of time before the meeting."
- ✅ **Good Incorrect** (Multi-hop logic mirrored): "No, the meeting is at 2:00 PM, and the laundry will finish at 2:15 PM, meaning you will be late."

**Examples of Good/Bad Unanswerable QAs:**

*Example 1: Grounded Premises*
- ❌ **Bad Premise (Hallucination)**: "Did I ask you to remind me to order pizza at this time?" (If pizza was never mentioned in the ledger, the evaluating model will easily guess this is an unanswerable hallucination probe).
- ✅ **Good Premise (Missing Detail)**: "What was the exact expiration date printed on the milk carton I was holding?" (The milk carton actually exists in the video, but the date is simply occluded/missing. This premise is indistinguishable from an answerable question).

*Example 2: Fabrication Quality*
- **Question**: "I'm thinking about the person who helped me with the puzzle. Did he wear glasses?" (Unanswerable because his face was off-camera).
- ❌ **Bad Distractor** (Vague/Short): "He was wearing sunglasses." (Evaluating model will guess the question is unanswerable because the choices lack rich narrative texture).
- ✅ **Good Distractor** (Specific & Grounded): "He was wearing thick black square-framed glasses that he kept adjusting while looking at the puzzle pieces."
"""


# ──────────────────────────────────────────────────────────────────────
# Markdown formatters — replace json.dumps() in prompt user functions
# for token-efficient, model-friendly structured text.
# ──────────────────────────────────────────────────────────────────────

def _fmt(value, default: str = "N/A") -> str:
    """Stringify a value, returning *default* for None/empty."""
    if value is None:
        return default
    if isinstance(value, list) and len(value) == 0:
        return default
    return str(value)


def format_qa_pair_markdown(qa: dict) -> str:
    """Render a QA pair dict as structured markdown."""
    lines: list[str] = []
    q = qa.get("question", {})
    a = qa.get("answer", {})
    meta = qa.get("metadata", {})

    # ── Question ──────────────────────────────────────────────────────
    lines.append("## Question")
    lines.append(f"**Text:** {_fmt(q.get('text'))}")
    lines.append(f"**Video:** {_fmt(q.get('video_id'))} | **Room:** {_fmt(q.get('room'))}")

    q_mods = q.get("modalities", [])
    if q_mods:
        lines.append(f"**Modalities:** {', '.join(q_mods)}")

    q_reasoning = q.get("question_reasoning")
    if q_reasoning:
        lines.append(f"**Reasoning:** {q_reasoning}")

    q_spans = q.get("time_spans", [])
    if q_spans:
        lines.append("**Time Spans:**")
        for span in q_spans:
            vid = span.get("video_id", q.get("video_id", "?"))
            start = span.get("start_time", span.get("start", "?"))
            end = span.get("end_time", span.get("end", "?"))
            lines.append(f"  - {vid} [{start} – {end}]")

    lines.append("")

    # ── Answer ────────────────────────────────────────────────────────
    lines.append("## Answer")
    is_answerable = a.get("is_answerable")
    lines.append(f"**Answerable:** {'Yes' if is_answerable else 'No'}")
    lines.append(f"**Text:** {_fmt(a.get('text'))}")

    evidence = a.get("evidence_list", [])
    if evidence:
        lines.append("### Evidence")
        for i, ev in enumerate(evidence, 1):
            ev_vid = ev.get("video_id", "?")
            ev_ts = ev.get("time_span", {})
            ev_start = ev_ts.get("start_time", ev_ts.get("start", "?"))
            ev_end = ev_ts.get("end_time", ev_ts.get("end", "?"))
            ev_room = ev.get("room", "?")
            ev_mods = ", ".join(ev.get("modalities", []))
            lines.append(f"{i}. **{ev_vid}** [{ev_start} – {ev_end}] | Room: {ev_room}")
            lines.append(f"   Reason: {_fmt(ev.get('reason'))}")
            if ev_mods:
                lines.append(f"   Modalities: {ev_mods}")

    choices = a.get("answer_choices", [])
    if choices:
        lines.append("### Choices")
        for i, ch in enumerate(choices, 1):
            ch_type = ch.get("choice_type", "?")
            ch_text = ch.get("text", "?")
            lines.append(f"{i}. [{ch_type}] {ch_text}")
            explanation = ch.get("explanation")
            if explanation:
                lines.append(f"   _Explanation: {explanation}_")

    lines.append("")

    # ── Metadata ──────────────────────────────────────────────────────
    lines.append("## Metadata")
    lines.append(f"**Skill:** {_fmt(meta.get('skill'))} | **Primary Video:** {_fmt(meta.get('primary_video_id'))}")
    skill_reasoning = meta.get("skill_reasoning")
    if skill_reasoning:
        lines.append(f"**Skill Reasoning:** {skill_reasoning}")

    _skip_keys = {"skill", "skill_reasoning", "primary_video_id", "qa_id", "original_idx"}
    extra_meta = {k: v for k, v in meta.items() if k not in _skip_keys and v}
    if extra_meta:
        for k, v in extra_meta.items():
            if isinstance(v, dict):
                lines.append(f"**{k}:**")
                for mk, mv in v.items():
                    lines.append(f"  - {mk}: {mv}")
            elif isinstance(v, list):
                lines.append(f"**{k}:** {', '.join(str(x) for x in v)}")
            else:
                lines.append(f"**{k}:** {v}")

    return "\n".join(lines)


def format_verification_score_markdown(score: dict) -> str:
    """Render a verification score dict as structured markdown."""
    lines: list[str] = []

    lines.append("## Verification Score")
    is_correct = score.get("is_correct")
    is_guessable = score.get("is_guessable")
    contains_pii = score.get("contains_pii")

    is_salvageable = score.get("is_salvageable", True)

    lines.append(
        f"**Is Correct:** {'Yes' if is_correct else 'No'} | "
        f"**Is Guessable:** {'Yes' if is_guessable else 'No'} | "
        f"**Contains PII:** {'Yes' if contains_pii else 'No'} | "
        f"**Is Salvageable:** {'Yes' if is_salvageable else 'No'}"
    )

    factual = score.get("factual_correctness_score", "?")
    objective = score.get("objective_correctness_score", "?")
    causal = score.get("causal_answerability_score", "?")
    naturalness = score.get("naturalness_score", "?")
    lines.append(f"**Factual:** {factual} | **Objective:** {objective} | **Causal:** {causal} | **Naturalness:** {naturalness}")

    lines.append("")
    lines.append("### Reasoning")
    reasoning_keys = [
        ("factual_correctness_reasoning", "Factual"),
        ("objective_correctness_reasoning", "Objective"),
        ("causal_answerability_reasoning", "Causal"),
        ("naturalness_reasoning", "Naturalness"),
        ("guessability_justification", "Guessability"),
        ("privacy_audit_reasoning", "Privacy"),
    ]
    for key, label in reasoning_keys:
        val = score.get(key)
        if val:
            lines.append(f"- **{label}:** {val}")

    conf_score = score.get("confidence_score")
    conf_reasoning = score.get("confidence_reasoning")
    if conf_score is not None:
        lines.append(f"- **Confidence:** {conf_score}")
    if conf_reasoning:
        lines.append(f"  _{conf_reasoning}_")

    suggestions = score.get("suggestions", [])
    if suggestions:
        lines.append("")
        lines.append("### Suggestions")
        for i, s in enumerate(suggestions, 1):
            lines.append(f"{i}. {s}")

    suggested_chunks = score.get("suggested_chunks", [])
    if suggested_chunks:
        lines.append("")
        lines.append("### Suggested Chunks")
        for sc in suggested_chunks:
            if hasattr(sc, "model_dump"):
                sc = sc.model_dump()
            elif not isinstance(sc, dict):
                continue
            vid = sc.get("video_id", "?")
            sc_start = sc.get("start_time", "?")
            sc_end = sc.get("end_time", "?")
            reason = sc.get("relevance_reason", "")
            lines.append(f"- {vid} [{sc_start} – {sc_end}] — {reason}")

    return "\n".join(lines)


def format_context_summary_markdown(summary: dict) -> str:
    """Render a context summary dict as structured markdown key-value list."""
    if not summary or not isinstance(summary, dict):
        return "_No context summary available._"

    lines: list[str] = []
    lines.append("## Context Summary")
    for key, value in summary.items():
        if isinstance(value, dict):
            lines.append(f"**{key}:**")
            for k, v in value.items():
                lines.append(f"  - {k}: {v}")
        elif isinstance(value, list):
            lines.append(f"**{key}:**")
            for item in value:
                if isinstance(item, dict):
                    parts = [f"{k}={v}" for k, v in item.items()]
                    lines.append(f"  - {', '.join(parts)}")
                else:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"**{key}:** {value}")
    return "\n".join(lines)

