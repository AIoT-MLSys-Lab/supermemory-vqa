"""
Common utilities shared across pipeline_v2 modules.

Consolidates functions that were previously duplicated across verifier.py,
stage2.py, verifier_loop.py, and integrity_utils.py.
"""

import copy
import datetime
import logging
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Union

import ffmpeg

from .config import PIPELINE_V2_CONFIG
from .video_utils import timestamp_to_seconds, validate_video_clip

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Path / ID helpers
# ──────────────────────────────────────────────────────────────────────

def strip_ext(vid: Optional[str]) -> Optional[str]:
    """Remove file extension from video ID if present."""
    return os.path.splitext(vid)[0] if vid else vid


# ──────────────────────────────────────────────────────────────────────
# Time parsing / formatting
# ──────────────────────────────────────────────────────────────────────

def to_seconds(value: Union[str, float, int, None]) -> Optional[float]:
    """Convert a timestamp string, int, or float to seconds. Returns None for None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return timestamp_to_seconds(value)


def format_seconds(seconds: float) -> str:
    """Convert seconds to a human-readable M:SS string."""
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_abs_time(unix_ts: float) -> str:
    """Format absolute Unix timestamp as human-readable datetime string."""
    try:
        return datetime.datetime.fromtimestamp(unix_ts).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError, OverflowError):
        return "Unknown"


# ──────────────────────────────────────────────────────────────────────
# Span / temporal helpers
# ──────────────────────────────────────────────────────────────────────

def get_span_bounds(span: Dict[str, Any]) -> tuple[Optional[Union[str, float]], Optional[Union[str, float]]]:
    """Support both {start,end} and {start_time,end_time} formats."""
    if not isinstance(span, dict):
        return None, None
    start_val = span.get('start')
    end_val = span.get('end')
    if start_val is None:
        start_val = span.get('start_time')
    if end_val is None:
        end_val = span.get('end_time')
    return start_val, end_val


def absolute_seconds(
    video_id: Optional[str],
    local_seconds: Optional[float],
    video_offsets: Dict[str, float],
    first_video_start_time: float,
) -> Optional[float]:
    """Compute absolute timestamp from video-local seconds."""
    if video_id is None or local_seconds is None:
        return None
    if video_id not in video_offsets:
        return None
    return first_video_start_time + video_offsets[video_id] + local_seconds


def filter_causal_answer_evidence(
    qa_pair: Dict[str, Any],
    video_offsets: Dict[str, float],
    first_video_start_time: float,
) -> int:
    """Remove answer evidence that occurs after question start.

    Modifies qa_pair in-place. Returns number of removed items.
    Raises ValueError if a video ID cannot be matched to the offsets.
    """
    question = qa_pair.get('question', {})
    q_vid = strip_ext(question.get('video_id'))

    q_spans = question.get('time_spans', [])
    if not q_spans:
        if 'time_span' in question:
            raise ValueError("QA pair uses legacy 'time_span' field. Migrate to 'time_spans' list.")
        return 0

    # Find absolute time of the earliest question span start
    q_min_abs = None
    for span in q_spans:
        q_start_val, _ = get_span_bounds(span)
        q_local_sec = to_seconds(q_start_val)
        if q_local_sec is not None:
            span_vid = strip_ext(span.get('video_id')) or q_vid
            if span_vid not in video_offsets:
                raise ValueError(f"Question span video ID '{span_vid}' missing from ledger offsets.")
            q_video_offset = video_offsets[span_vid]
            abs_time = first_video_start_time + q_video_offset + q_local_sec
            if q_min_abs is None or abs_time < q_min_abs:
                q_min_abs = abs_time

    if q_min_abs is None:
        return 0

    # Keep `or []` to tolerate explicit `None` values from model outputs.
    original_evidence = qa_pair.get('answer', {}).get('evidence_list', []) or []
    causal_evidence = []
    removed = 0
    for ev in original_evidence:
        ev_vid = strip_ext(ev.get('video_id'))
        ev_ts = ev.get('time_span', {})
        ev_start_val, ev_end_val = get_span_bounds(ev_ts)
        # Use evidence END time: evidence must fully conclude before question starts
        ev_end_sec = to_seconds(ev_end_val)
        if ev_end_sec is None:
            ev_end_sec = to_seconds(ev_start_val)
        if ev_end_sec is None or not ev_vid:
            continue

        if ev_vid not in video_offsets:
            raise ValueError(f"Evidence video ID '{ev_vid}' missing from ledger offsets.")

        ev_video_offset = video_offsets[ev_vid]
        ev_end_abs = first_video_start_time + ev_video_offset + ev_end_sec
        if ev_end_abs <= q_min_abs:
            causal_evidence.append(ev)
        else:
            removed += 1

    if 'answer' in qa_pair:
        qa_pair['answer']['evidence_list'] = causal_evidence
    return removed


# ──────────────────────────────────────────────────────────────────────
# Video clip extraction
# ──────────────────────────────────────────────────────────────────────

def extract_clip(
    video_path: str,
    start_time: Union[str, float],
    end_time: Union[str, float],
    output_path: str,
) -> bool:
    """Extract a specific clip from a video using FFmpeg.

    Returns True if successful, False if skipped or failed.
    """
    try:
        start_sec = timestamp_to_seconds(start_time) if isinstance(start_time, str) else float(start_time)
        end_sec = timestamp_to_seconds(end_time) if isinstance(end_time, str) else float(end_time)
        duration = end_sec - start_sec
        if duration < 0:
            logger.warning(f"Invalid duration {duration} for clip {start_time}-{end_time}, skipping.")
            return False

        if duration == 0:
            logger.info(f"Duration 0.0 for clip {start_time}-{end_time}. Extracting a single frame.")
            (
                ffmpeg
                .input(video_path, ss=start_sec)
                .output(
                    output_path,
                    vframes=1,
                    vcodec='libx264',
                    acodec='aac',
                    format='mp4',
                    **{'avoid_negative_ts': 'make_zero'}
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            return True

        (
            ffmpeg
            .input(video_path, ss=start_sec, t=duration)
            .output(
                output_path,
                vcodec='libx264',
                acodec='aac',
                r=4,  # 4fps for high resolution requirement
                format='mp4',
                **{'avoid_negative_ts': 'make_zero'}
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
        return True
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error: {e.stderr.decode()}")
        return False
    except Exception as e:
        logger.error(f"Error extracting clip: {e}")
        return False


def get_or_extract_clip(
    video_id: str,
    video_path: str,
    start_sec: float,
    end_sec: float,
    storage_dir: str,
) -> Optional[str]:
    """Returns the path to a clip, extracting it if it doesn't exist or is empty."""
    max_dur = PIPELINE_V2_CONFIG.get("max_clip_duration", 120.0)
    if end_sec - start_sec > max_dur:
        logger.info(f"Truncating clip {video_id} from {end_sec - start_sec:.1f}s to {max_dur:.1f}s")
        end_sec = start_sec + max_dur

    safe_vid = video_id.replace("/", "_").replace("\\", "_")
    safe_name = f"clip_{safe_vid}_{start_sec:.1f}s_{end_sec:.1f}s.mp4".replace(".", "-")
    if safe_name.endswith("-mp4"):
        safe_name = safe_name[:-4] + ".mp4"
    else:
        safe_name += ".mp4"

    out_path = os.path.join(storage_dir, safe_name)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        if validate_video_clip(out_path):
            return out_path
        else:
            logger.warning(f"Cached clip {out_path} failed validation. Re-extracting...")

    logger.info(f"Extracting clip {video_id} [{start_sec:.1f}s - {end_sec:.1f}s] to {out_path}")
    if extract_clip(video_path, start_sec, end_sec, out_path):
        if validate_video_clip(out_path):
            return out_path
        else:
            logger.error(f"Extracted clip {out_path} failed validation. Skipping.")
    return None


# ──────────────────────────────────────────────────────────────────────
# QA validation helpers
# ──────────────────────────────────────────────────────────────────────

def validate_qa_timestamps(
    qa: Dict[str, Any],
    video_durations: Dict[str, float],
) -> bool:
    """Validate that all timestamps in a QA pair fall within video durations.

    Returns True if valid, False if any timestamp is out of bounds.
    """
    if not qa:
        return True

    q = qa.get('question', {})
    q_vid = q.get('video_id')
    if q_vid and q_vid in video_durations:
        q_spans = q.get('time_spans', [])
        if not q_spans:
            if 'time_span' in q:
                logger.error(f"QA pair uses legacy 'time_span' field. Must use 'time_spans' list.")
            else:
                logger.warning(f"QA pair has no 'time_spans' for question in video {q_vid}.")
            return False
        for ts in q_spans:
            start_sec = timestamp_to_seconds(ts.get('start_time', '0:00'))
            end_sec = timestamp_to_seconds(ts.get('end_time', '0:00'))
            limit = video_durations.get(q_vid, 0)
            if start_sec > limit + 0.1 or end_sec > limit + 0.1:
                logger.warning(f"Validation failed: Question span {start_sec}-{end_sec} outside {q_vid} duration {limit}")
                return False

    ans = qa.get('answer', {})
    for ev in ans.get('evidence_list', []):
        e_vid = ev.get('video_id')
        if e_vid and e_vid in video_durations:
            ts = ev.get('time_span', {})
            start_sec = timestamp_to_seconds(ts.get('start_time', '0:00'))
            end_sec = timestamp_to_seconds(ts.get('end_time', '0:00'))
            limit = video_durations.get(e_vid, 0)
            if start_sec > limit + 0.1 or end_sec > limit + 0.1:
                logger.warning(f"Validation failed: Evidence span {start_sec}-{end_sec} outside {e_vid} duration {limit}")
                return False
    return True


def get_question_video_id(
    qa: Dict[str, Any],
    video_offsets: Dict[str, float],
) -> str:
    """Determine the primary video ID for a QA pair based on earliest question span."""
    if not qa:
        return 'unknown'
    q = qa.get('question', {})
    q_vid = strip_ext(q.get('video_id'))
    q_spans = q.get('time_spans', [])

    earliest_video = q_vid
    min_sec = float('inf')

    for span in q_spans:
        span_vid = strip_ext(span.get('video_id')) or q_vid
        start_val = span.get('start_time') or span.get('start')
        if start_val and span_vid in video_offsets:
            try:
                sec = timestamp_to_seconds(start_val)
                abs_t = video_offsets[span_vid] + sec
                if abs_t < min_sec:
                    min_sec = abs_t
                    earliest_video = span_vid
            except Exception:
                pass

    return earliest_video or 'unknown'


def build_cross_day_summary(qa_pairs: List[Dict[str, Any]]) -> str:
    """Build a compact summary of QAs from other days for skill balance guidance.

    Produces a compact block (~10-20 lines total) containing:
      - Skill distribution counts
      - Answerable/unanswerable ratio
      - Covered video IDs and time regions
    """
    skill_counts: Counter = Counter()
    answerable_count = 0
    unanswerable_count = 0
    video_coverage: dict[str, list[str]] = defaultdict(list)

    for qa in qa_pairs:
        skill = qa.get('metadata', {}).get('skill', 'unknown')
        skill_counts[skill] += 1

        is_ans = qa.get('answer', {}).get('is_answerable', True)
        if is_ans:
            answerable_count += 1
        else:
            unanswerable_count += 1

        for ev in qa.get('answer', {}).get('evidence_list', []):
            vid = ev.get('video_id', '')
            ts = ev.get('time_span', {})
            start = ts.get('start_time', '?')
            if vid and start != '?':
                video_coverage[vid].append(start)

    lines = [f"Total: {len(qa_pairs)} QAs (answerable: {answerable_count}, unanswerable: {unanswerable_count})"]
    lines.append("Skill distribution: " + ", ".join(f"{s}({c})" for s, c in skill_counts.most_common()))

    if video_coverage:
        lines.append("Evidence coverage by video:")
        for vid, starts in sorted(video_coverage.items()):
            sample = starts[:3]
            suffix = f" +{len(starts)-3} more" if len(starts) > 3 else ""
            lines.append(f"  - {vid}: {len(starts)} evidence spans (e.g. {', '.join(sample)}{suffix})")

    return "\n".join(lines)


def preserve_fields_from_original(enhanced_qa: Dict[str, Any], orig_qa: Dict[str, Any]) -> None:
    """Restore fields the enhancer may have dropped or overwritten.

    Modifies enhanced_qa in-place.
    """
    if str(orig_qa.get('question', {}).get('time_spans')) != str(enhanced_qa.get('question', {}).get('time_spans')) or \
       str(orig_qa.get('question', {}).get('video_id')) != str(enhanced_qa.get('question', {}).get('video_id')):
        logger.warning(
            f"SALVAGE modified question timing or video_id for qa_id "
            f"{enhanced_qa.get('metadata', {}).get('qa_id')}. Retriever context may be stale."
        )

    # answer_choices
    orig_choices = orig_qa.get('answer', {}).get('answer_choices', [])
    enh_choices = enhanced_qa.get('answer', {}).get('answer_choices', [])
    if not enh_choices and orig_choices:
        enhanced_qa.setdefault('answer', {})['answer_choices'] = orig_choices

    # is_answerable
    orig_ans = orig_qa.get('answer', {}).get('is_answerable')
    enh_ans = enhanced_qa.get('answer', {}).get('is_answerable')
    if enh_ans is None:
        fallback = orig_ans if orig_ans is not None else orig_qa.get('question', {}).get('is_answerable')
        if fallback is not None:
            enhanced_qa.setdefault('answer', {})['is_answerable'] = fallback

    # question_reasoning
    orig_reasoning = orig_qa.get('question', {}).get('question_reasoning')
    if not enhanced_qa.get('question', {}).get('question_reasoning') and orig_reasoning:
        enhanced_qa.setdefault('question', {})['question_reasoning'] = orig_reasoning

    # skill
    orig_skill = orig_qa.get('metadata', {}).get('skill')
    if orig_skill:
        enhanced_qa.setdefault('metadata', {})['skill'] = orig_skill
