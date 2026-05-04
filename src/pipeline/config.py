import os
from typing import Dict, Any
from dotenv import load_dotenv

# Auto-load .env variables before config starts
load_dotenv()

# Project root detection
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Centralized configuration for Pipeline v2
PIPELINE_V2_CONFIG: Dict[str, Any] = {
    # Models
    "stage1_model": "gemini-3-flash-preview",
    "stage1_fallback_model": "gemini-3.1-pro-preview",
    
    "stage2_planner_model": "gemini-3.1-pro-preview",
    "stage2_planner_fallback_model": None, # Planner does not use fallback
    
    "stage2_retriever_model": "gemini-3-flash-preview",
    "stage2_retriever_fallback_model": "gemini-3.1-pro-preview",
    
    "stage2_verifier_model": "gemini-3.1-pro-preview",
    "stage2_verifier_fallback_model": "gemini-3.1-pro-preview",
    
    "stage2_enhancer_model": "gemini-3-flash-preview",
    "stage2_enhancer_fallback_model": "gemini-3.1-pro-preview",
    
    # Video Chunking Settings
    "chunk_duration": 120,
    "max_clip_duration": 180,
    "overlap_duration": 0,
    "min_chunk_duration": 90,
    "max_chunks_per_video": -1,
    "chunk_fps": 4,
    "chunk_cache_dir": os.path.join(_PROJECT_ROOT, "tmp"),

    # WhisperX Settings
    "whisper_model": "large-v3",
    "whisper_device": "cuda",
    "hf_token": os.getenv("HF_TOKEN"),

    # Generation Parameters
    "target_qa_per_minute": 2,
    "qa_batch_size": 50,
    "temperature": 0.7,
    "qa_file": None,
    
    # Execution Strategy
    "max_concurrent_workers": 16,
    "batch_job_timeout_hours": 6,
    "max_verification_loops": 3,
    "force_reprocess": False,
    
    # Verification Thresholds
    "min_confidence": 0.6,
    "fallback_confidence_thresholds": ["Low", "Medium"],

    # EgoBlur Settings
    "egoblur_bin": "/research/nfs_zhang_13664/samiul/anaconda3/envs/supermemory/bin/egoblur-gen1",
    "egoblur_face_model": os.path.join(_PROJECT_ROOT, "models", "ego_blur_face_gen1.jit"),
    "egoblur_lp_model": os.path.join(_PROJECT_ROOT, "models", "ego_blur_lp_gen1.jit"),
}
