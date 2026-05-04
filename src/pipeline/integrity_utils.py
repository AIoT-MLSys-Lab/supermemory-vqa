"""
Utility functions for verifying data integrity in the pipeline.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def validate_temporal_integrity(qa_pairs: List[Dict[str, Any]], super_ledger: Dict[str, Any], label: str = "Pipeline") -> bool:
    """Verify that all QA pairs are temporally within bounds and causally ordered."""
    from .video_utils import timestamp_to_seconds
    from .common_utils import strip_ext
    
    video_meta = {
        strip_ext(v['video_id']): {'start_time': v['start_time'], 'duration': v['duration']} 
        for v in super_ledger.get('videos', [])
    }
    
    stats = {
        "total_annotations": 0,
        "bound_violations": 0,
        "causal_violations": 0,
        "missing_video_id": 0
    }
    violations = []

    for idx, ann_full in enumerate(qa_pairs):
        # Handle potential nested structure from different pipeline stages
        ann = ann_full.get('qa_pair', ann_full)
        stats["total_annotations"] += 1
        
        q = ann.get('question', {})
        q_video_id = strip_ext(q.get('video_id'))
        q_spans = q.get('time_spans', [])
        if not q_spans and 'time_span' in q:
            q_spans = [q['time_span']]
        
        q_abs_starts = []
        
        for span in q_spans:
            start_str = span.get('start_time')
            end_str = span.get('end_time', start_str)
            
            span_vid = strip_ext(span.get('video_id')) or q_video_id
            
            if not span_vid or span_vid not in video_meta:
                stats["missing_video_id"] += 1
                violations.append(f"Q[{idx}]: Validating question span {start_str}-{end_str} failed. Video ID '{span_vid}' is missing from ledger.")
                continue
                
            duration = video_meta[span_vid]['duration']
            try:
                start_sec = timestamp_to_seconds(start_str)
                end_sec = timestamp_to_seconds(end_str)
            except (ValueError, TypeError):
                continue
            
            if start_sec < -0.1 or start_sec > duration + 1.0 or end_sec < -0.1 or end_sec > duration + 1.0:
                stats["bound_violations"] += 1
                violations.append(f"Q[{idx}]: Question span {start_str}-{end_str} out of bounds for {span_vid} (duration {duration}s).")
            
            q_abs_starts.append(video_meta[span_vid]['start_time'] + start_sec)

        ans = ann.get('answer', {})
        evidence_list = ans.get('evidence_list', [])
        e_abs_ends = []
        
        for e_idx, e in enumerate(evidence_list):
            e_video_id = strip_ext(e.get('video_id'))
            e_span = e.get('time_span', {})
            e_start_str = e_span.get('start_time')
            e_end_str = e_span.get('end_time', e_start_str)
            
            if not e_video_id or e_video_id not in video_meta:
                stats["missing_video_id"] += 1
                violations.append(f"Q[{idx}] E[{e_idx}]: Validating evidence span {e_start_str}-{e_end_str} failed. Video ID '{e_video_id}' is missing from ledger.")
                continue
                
            e_duration = video_meta[e_video_id]['duration']
            try:
                e_start_sec = timestamp_to_seconds(e_start_str)
                e_end_sec = timestamp_to_seconds(e_end_str)
            except (ValueError, TypeError):
                continue
            
            if e_start_sec < -0.1 or e_start_sec > e_duration + 1.0 or e_end_sec < -0.1 or e_end_sec > e_duration + 1.0:
                stats["bound_violations"] += 1
                violations.append(f"Q[{idx}] E[{e_idx}]: Evidence span {e_start_str}-{e_end_str} out of bounds for {e_video_id} (duration {e_duration}s).")
            
            e_abs_ends.append(video_meta[e_video_id]['start_time'] + e_end_sec)

        # Causal check: All evidence ends must be before the earliest question start
        if q_abs_starts and e_abs_ends:
            min_q_start = min(q_abs_starts)
            max_e_end = max(e_abs_ends)
            
            # Allow 0.5s tolerance for slight overlap in consecutive videos
            if max_e_end > min_q_start + 0.5:
                stats["causal_violations"] += 1
                violations.append(f"Q[{idx}]: Causal violation! Max evidence end is after min question start (Gap: {min_q_start - max_e_end}s).")

    logger.info("=" * 50)
    logger.info(f" TEMPORAL INTEGRITY REPORT ({label}) ".center(50, "="))
    logger.info("=" * 50)
    logger.info(f"Total Annotations Checked: {stats['total_annotations']}")
    logger.info(f"Bound Violations:         {stats['bound_violations']}")
    logger.info(f"Causal Violations:        {stats['causal_violations']}")
    if stats['missing_video_id']:
        logger.warning(f"Missing Video IDs:        {stats['missing_video_id']}")
    
    if violations:
        logger.error(f"{label} verification found {len(violations)} issues.")
        for v in violations[:5]: 
            logger.warning(f"  - {v}")
        if len(violations) > 5:
            logger.warning(f"  ... and {len(violations)-5} more.")
        return False
    else:
        logger.info(f"SUCCESS: {label} temporal integrity checks passed.")
        return True
