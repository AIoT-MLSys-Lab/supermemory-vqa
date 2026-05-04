"""
Stage 1: Caption Narration and Segment schemas and prompt.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from .common import TimeSpan

SpeakerLabels = Literal[
    'User', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
]

PersonLabels = Literal[
    'User', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
]

class TranscriptLine(BaseModel):
    """A single line of audio transcript or sound event"""
    speaker: Optional[SpeakerLabels] = Field(
        None,
        description="The speaker identifier ('User' or 'A'-'Z'). Leave as null for non-vocal environmental sounds."
    )
    transcript: str = Field(
        ...,
        description="The spoken text. If the speaker is null (for environmental sounds like a car honk), enclose the sound description in brackets, e.g., '[Car honks]'."
    )

class PersonDetail(BaseModel):
    """Details about a specific person visible or active in the segment"""
    description: str = Field(
        ...,
        description="Physical description of the person (gender, what they are wearing) and their role/actions in this timespan."
    )
    person: PersonLabels = Field(
        ...,
        description="The person identifier ('A'-'Z') corresponding to the speaker labels."
    )

class SegmentDescription(BaseModel):
    """Description of a video segment based strictly on what is in the video. Descriptive fields first."""
    activities: str = Field(
        ...,
        description="Detailed description of what the glass wearer is doing."
    )
    environment: Optional[str] = Field(
        None,
        description="Location, room type, and notable background elements."
    )
    visible_text: Optional[str] = Field(
        None,
        description="Exact transcription of any visible signs, labels, or numbers via OCR."
    )
    objects: Optional[List[str]] = Field(
        None,
        description="List of key manipulated or visible objects (e.g., ['keys', 'coffee mug'])."
    )
    audio_transcript: Optional[List[TranscriptLine]] = Field(
        None,
        description="Chronological list of spoken lines and significant sounds."
    )
    people: Optional[List[PersonDetail]] = Field(
        None,
        description="List of people present in the scene, their physical descriptions, roles and activities."
    )

def get_stage1_caption_schema(video_id: str) -> type['ChunkCaptionOutput']:
    """
    Dynamically creates Pydantic classes for caption generation where video_id is
    constrained to the provided ID.
    """
    video_id_type = Literal[video_id] # type: ignore

    class VideoSegment(BaseModel):
        """A single chronological segment within a video chunk. Descriptive fields first."""
        description: SegmentDescription = Field(
            ...,
            description="The extracted details of the segment exactly as they appear in the video."
        )
        time_span: TimeSpan = Field(
            ...,
            description="Exact start and end time of this segment."
        )
        optimal_sampling_rate_reasoning: str = Field(
            ...,
            description="Reasoning for why this optimal sampling rate was chosen."
        )
        optimal_sampling_rate: Literal["low", "medium", "high"] = Field(
            None,
            description="The sampling rate the segment should need. For lots of movement or activities like sports, this should be high whereas when there is minimal movement, this should be low."
        )
        optimal_resolution_reasoning: str = Field(
            ...,
            description="Reasoning for why this optimal resolution was chosen."
        )
        optimal_resolution: Literal["low", "medium", "high"] = Field(
            None,
            description="The resolution to process the image in. For high fidelity activities like reading text, this should be high, for low fidelity like casual walking, this can be low."
        )
        importance_reasoning: str = Field(
            ...,
            description="Reasoning for why this importance level was chosen."
        )
        importance: Literal["low", "medium", "high"] = Field(
            ...,
            description="How important the activities are overall to a supermemory task."
        )
        confidence_reasoning: str = Field(
            ...,
            description="Reasoning for why this confidence level was chosen."
        )
        confidence: Literal["low", "medium", "high"] = Field(
            ...,
            description="How confident the model is about the accuracy of the segment description."
        )

    class ChunkCaptionOutput(BaseModel):
        """Output schema for Stage 1: Dense caption with segments. Descriptive fields first."""
        overall_summary: str = Field(
            ...,
            description="A comprehensive summary of all the events, key details, and narrative progression across the entire video chunk."
        )
        segments: List[VideoSegment] = Field(
            ...,
            description="List of continuous, non-overlapping segments in this chunk, strictly ordered by time."
        )
        video_id: video_id_type = Field(
            ...,
            description="Video ID matching the source video."
        )
        
    return ChunkCaptionOutput


def get_stage1_system_instruction() -> str:
    """
    Returns the static system instruction for Stage 1.
    Includes identity, objectives, required components, and output format.
    """
    return """
You are an expert egocentric video archivist assistant operating an AI wearable device. Your task is to intensely scrutinize the provided video segment and build an exhaustive, densely detailed chronological ledger of every single discernible action, event, interaction, object, and piece of text.

DO NOT output any internal thoughts or reasoning inside the final JSON output structure. The JSON output must strictly adhere to the requested schema. Use the internal thinking capability of the model to reason about the video content before generating the final JSON output.

### PRIVACY & DATA PROTECTION (CRITICAL)
Your descriptions MUST NOT include sensitive private information such as:
- ID card numbers, passports, or social security numbers.
- License plates on private vehicles.
- Private financial documents, credit card numbers, or passwords.
- Any other sensitive personal identification data.

**Exception**: Information visible in public outdoor spaces—such as phone numbers or addresses on billboards, storefronts, and public signs—is acceptable to include as it is widely accessible to the public.

### CONSISTENCY & GROUNDING (CRITICAL)
- **Check the Registry**: You will be provided with a "SESSION REGISTRY" containing people, objects, and text identified in previous chunks. You MUST use these exact labels and IDs if the entity reappears. Do not invent a new ID for an existing person.
- **Spatial Anchors**: Whenever describing objects or text, you MUST ground them spatially relative to the environment (e.g., "the red mug on the far left of the kitchen counter", "the text written on the whiteboard next to the door").

### CORE OBJECTIVES
The video chunk provided to you must be aggressively segmented into non-overlapping chronological timespans. The union of these timespans must cover the entire video chunk duration (from 00:00 to the end).

For EACH segment, you must evaluate the `importance` (how important the activities are overall to a supermemory task) ranging from "low", "medium", to "high".
CRITICAL NOTE: The presence of fields in the segment descriptions MUST be based strictly on what is in the video, NOT the importance of the segment. Do not skip details just because importance is low, if the details are physically present. 

### REQUIRED SEGMENT COMPONENTS
For each segment, strictly adhere to the following data structure:
1. `time_span`: Provide exact `start_time` and `end_time` (MM:SS). Segments must be continuous with no gaps.
2. `optimal_sampling_rate`: Provide the necessary rate to extract sufficient detail in later stages. This MUST be preceded by `optimal_sampling_rate_reasoning`.
3. `optimal_resolution`: Provide the necessary resolution to extract sufficient detail in later stages. This MUST be preceded by `optimal_resolution_reasoning`.
4. `importance`: Classify as "low", "medium", or "high" determining overall value to a memory task. This MUST be preceded by `importance_reasoning`.
5. `confidence`: Classify as "low", "medium", or "high" based on how clearly you can discern the details. This MUST be preceded by `confidence_reasoning`.
6. `description`: Inside the description object, categorize observations based on video content:
    - `activities`: A vivid narrative of the user's primary actions and gaze (e.g., "The user picks up a blue coffee mug with their right hand and brings it to their mouth. Their gaze briefly shifts to the laptop screen showing a spreadsheet.").
    - `objects`: List all distinct, identifiable objects manipulated or clearly in focus (e.g., "blue coffee mug", "black laptop", "silver keys").
    - `environment`: Describe the setting (e.g., "A brightly lit modern kitchen with marble countertops"). Describe changes if transitioning between areas.
    - `people`: If other individuals are visible, uniquely identify them (Person A, Person B) and describe their appearance (gender, clothing, notable features) and actions relative to the user.
    - `visible_text`: Transcribe EVERYTHING legible (labels, documents, signs, screens). Be exact.
    - `audio_transcript`: You will be provided with an automatically generated, diarized transcript (e.g., SPEAKER_00, SPEAKER_01). Your task is to align this provided transcript with the visual events and assign the speakers to the actual physical people visible in the scene (e.g. Person A, Person B) or to the User wearing the camera based on the audiovisual context. You must also add non-speech sounds explicitly into the transcript enclosed in square brackets (e.g., `[Car honks]`, `[Dog barks]`).

### OUTPUT FORMAT
1. Begin with an `overall_summary` field containing a single paragraph synthesizing the major events, narrative flow, and key settings across the entire video chunk.
2. Follow with the `segments` list containing the meticulously detailed sequential timespans describing everything observable in the video.
3. Include the exact `video_id` as specified in the required schema.
4. Ensure no overlapping timespans and no chronological gaps between segments.
"""

def get_stage1_timing_block(
    current_start_time: float = None, 
    current_end_time: float = None, 
    session_start_time: float = None,
    video_start_offset: float = 0.0,
    transcript_chunk: list = None
) -> str:
    """Returns the targeted block for CURRENT VIDEO TIMING.
    
    All transcript timestamps passed in must already be chunk-relative
    (i.e. shifted so the chunk starts at 0.0). The model will see both the
    video and the transcript starting from 00:00.
    """
    if current_start_time is None or current_end_time is None:
        return ""

    import datetime
    start_dt = datetime.datetime.fromtimestamp(current_start_time)
    end_dt = datetime.datetime.fromtimestamp(current_end_time)
    
    start_str = start_dt.strftime('%Y-%m-%d %H:%M (%A)')
    end_str = end_dt.strftime('%Y-%m-%d %H:%M (%A)')
    
    rel_msg = ""
    if session_start_time is not None and session_start_time > 0:
        rel_start = current_start_time - session_start_time
        # Only show relative time if it's sane (less than 100 hours)
        if 0 <= rel_start < 360000:
            m, s = divmod(int(rel_start), 60)
            h, m = divmod(m, 60)
            rel_msg = f" This chunk starts {h:02d}:{m:02d}:{s:02d} relative to the first video in the session."

    chunk_dur = current_end_time - current_start_time
    m, s = divmod(int(chunk_dur), 60)
    limit_str = f"{m:02d}:{s:02d}"
    block = f"\n### CURRENT VIDEO TIMING\nThe video chunk you are processing was recorded from {start_str} to {end_str}.{rel_msg}\n"
    block += f"All segment timespans in your output must be relative to the start of THIS CHUNK (00:00) and MUST NOT exceed the precise end of this chunk ({limit_str}). Any timespan > {limit_str} is invalid.\n"
    
    if transcript_chunk:
        block += "\n### AUDIO TRANSCRIPT\n"
        block += "Here is the automatically generated diarized transcript for this chunk. Timestamps are aligned to the start of this chunk (00:00). DO NOT alter the text.\n"
        block += "Align this transcript with the visual events correctly, assign physical people correctly, and insert non-speech sounds [like this].\n\n"
        for line in transcript_chunk:
            m_s, s_s = divmod(int(line['start']), 60)
            m_e, s_e = divmod(int(line['end']), 60)
            block += f"[{m_s:02d}:{s_s:02d} - {m_e:02d}:{s_e:02d}] {line.get('speaker', 'UNKNOWN')}: {line.get('text', '')}\n"
            
    return block

def get_stage1_caption_prompt(
    current_start_time: float = None, 
    current_end_time: float = None, 
    session_start_time: float = None,
    video_start_offset: float = 0.0,
    transcript_chunk: list = None
) -> str:
    """
    Get the legacy full prompt for Stage 1. 
    Maintained for compatibility with non-sequential Stage 1.
    """
    instructions = get_stage1_system_instruction()
    timing = get_stage1_timing_block(current_start_time, current_end_time, session_start_time, video_start_offset, transcript_chunk)
    return instructions + timing

def get_stage1_context_history(
    previous_captions: list, 
    max_context_chunks: int = 30,
    session_registry: dict = None
) -> str:
    """Returns the ### CONTEXT FROM PREVIOUS SEGMENTS block for prefix caching."""
    context_lines = []
    
    if session_registry:
        context_lines.extend([
            "",
            "### SESSION REGISTRY",
            "This registry contains all unique people identified in this session so far.",
            "You MUST use these exact labels and IDs to maintain consistency.",
            ""
        ])
        
        people = session_registry.get("people", {})
        if people:
            context_lines.append("#### People")
            context_lines.append("| ID | Physical Description |")
            context_lines.append("|---|---|")
            for pid, desc in people.items():
                # Clean up any newlines in description for table formatting
                desc_clean = desc.replace("\n", " ") if desc else ""
                context_lines.append(f"| {pid} | {desc_clean} |")
            context_lines.append("")

    if not previous_captions:
        return "\n".join(context_lines)
    
    # Apply sliding window — keep only the last N chunks
    context_chunks = previous_captions[-max_context_chunks:]
    
    context_lines.extend([
        "",
        "### CONTEXT FROM PREVIOUS SEGMENTS",
        "The following are summaries and detailed segment breakdowns from previously captioned chunks of this same recording session.",
        "Use these to maintain chronological consistency for objects, environment details, and visible text.",
        "Do NOT duplicate these descriptions in your output — only use them for context.",
        "",
    ])
    
    for cap in context_chunks:
        vid = cap.get('video_id', '?')
        abs_start = cap.get('start_time', 0)
        abs_end = cap.get('end_time', 0)
        summary = cap.get('overall_summary', 'No summary available.')
        segments = cap.get('segments', [])
        
        # Format absolute times as Date and Time
        def fmt_abs(s):
            import datetime
            dt = datetime.datetime.fromtimestamp(s)
            return dt.strftime('%Y-%m-%d %H:%M (%A)')
        
        header = f"#### [{vid} | {fmt_abs(abs_start)} to {fmt_abs(abs_end)}]"
        context_lines.append(f"{header}")
        context_lines.append(f"**Chunk Summary**: {summary}")
        
        if segments:
            context_lines.append("**Segment Breakdown:**")
            for seg in segments:
                t = seg.get('time', '')
                desc = seg.get('description', '')
                objs = seg.get('objects', [])
                ocr = seg.get('visible_text', '')
                
                context_lines.append(f"- **{t}**: {desc}")
                if objs:
                    context_lines.append(f"  - *Objects*: {', '.join(objs)}")
                if ocr:
                    context_lines.append(f"  - *OCR*: {ocr}")
        
        context_lines.append("")
    
    return "\n".join(context_lines)

def get_stage1_caption_prompt_with_context(
    previous_captions: list, 
    max_context_chunks: int = 30,
    current_start_time: float = None,
    current_end_time: float = None,
    session_start_time: float = None,
    video_start_offset: float = 0.0,
    transcript_chunk: list = None,
    session_registry: dict = None
) -> str:
    """
    Get the Stage 1 prompt augmented with context from previously captioned chunks.
    Maintained for legacy compatibility.
    """
    base_prompt = get_stage1_caption_prompt(current_start_time, current_end_time, session_start_time, video_start_offset, transcript_chunk)
    history = get_stage1_context_history(previous_captions, max_context_chunks, session_registry)
    return base_prompt + "\n" + history
