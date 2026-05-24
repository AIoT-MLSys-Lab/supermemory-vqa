import hashlib
import json
import os
from typing import Dict, Any, Optional, Sequence
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
    "qa_generation_turn_multiplier": 1.5,
    
    # Execution Strategy
    "max_concurrent_workers": 16,
    "upload_parallelism": 2,
    "batch_job_timeout_hours": 6,
    "max_verification_loops": 3,
    "force_reprocess": False,
    "run_id": None,
    "upload_manifest_filename": "upload_manifest.jsonl",
    "run_state_filename": "run_state.jsonl",
    "sweep_stale_uploads_on_start": True,
    "stale_upload_cleanup_seconds": 3600,
    
    # Inference Runtime Settings
    "inference_max_retries": 5,
    "inference_max_file_retries": 3,
    "file_active_timeout_seconds": 300,
    "file_poll_interval_seconds": 5,
    "upload_retry_backoff_base_seconds": 2,
    "upload_retry_backoff_max_seconds": 60,
    "generation_retry_backoff_base_seconds": 2,
    "generation_retry_backoff_max_seconds": 60,
    "media_resolution": "MEDIA_RESOLUTION_HIGH",
    "thinking_budget": -1,
    "include_thoughts": True,
    "max_video_clips_per_request": 10,
    "max_caption_excerpts_per_request": 20,
    "temporal_tolerance_seconds": 0.5,
    "clip_fps": 4,
    "stage1_confidence_enabled": False,
    
    # Verification Thresholds
    "min_confidence": 0.6,
    "fallback_confidence_thresholds": ["Low", "Medium"],

    # EgoBlur Settings
    "egoblur_bin": "/research/nfs_zhang_13664/samiul/anaconda3/envs/supermemory/bin/egoblur-gen1",
    "egoblur_face_model": os.path.join(_PROJECT_ROOT, "models", "ego_blur_face_gen1.jit"),
    "egoblur_lp_model": os.path.join(_PROJECT_ROOT, "models", "ego_blur_lp_gen1.jit"),
}


def _normalise_config_mapping(loaded: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either flat config or a namespaced Hydra-style mapping."""
    loaded = dict(loaded)
    loaded.pop("defaults", None)
    for key in ("pipeline_v2", "pipeline"):
        value = loaded.get(key)
        if isinstance(value, dict):
            return value
    return loaded


def _apply_omegaconf_overrides(
    base_config: Dict[str, Any],
    overrides: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Apply Hydra/OmegaConf dotlist overrides to a plain mapping."""
    if not overrides:
        return base_config
    try:
        from omegaconf import OmegaConf
    except ImportError as exc:
        raise RuntimeError(
            "Config overrides require hydra-core/OmegaConf. Install requirements.txt first."
        ) from exc

    cfg = OmegaConf.merge(OmegaConf.create(base_config), OmegaConf.from_dotlist(list(overrides)))
    loaded = OmegaConf.to_container(cfg, resolve=True) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Config overrides must resolve to a mapping.")
    return _normalise_config_mapping(loaded)


def _load_hydra_config(config_path: str, overrides: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Compose a Hydra config file and return a plain resolved mapping."""
    try:
        from hydra import compose, initialize_config_dir
        from omegaconf import OmegaConf
    except ImportError as exc:
        raise RuntimeError(
            "Hydra config files require hydra-core. Install requirements.txt first."
        ) from exc

    config_abspath = os.path.abspath(config_path)
    config_dir = os.path.dirname(config_abspath)
    config_name = os.path.splitext(os.path.basename(config_abspath))[0]

    with initialize_config_dir(version_base=None, config_dir=config_dir):
        cfg = compose(config_name=config_name, overrides=list(overrides or []))

    loaded = OmegaConf.to_container(cfg, resolve=True) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Hydra config must resolve to a mapping: {config_path}")
    return _normalise_config_mapping(loaded)


def load_pipeline_v2_config(
    config_path: Optional[str] = None,
    overrides: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Optionally merge a JSON file or Hydra-composed YAML into PIPELINE_V2_CONFIG."""
    if not config_path:
        if overrides:
            loaded = _apply_omegaconf_overrides(PIPELINE_V2_CONFIG, overrides)
            PIPELINE_V2_CONFIG.update(loaded)
        return PIPELINE_V2_CONFIG

    if config_path.lower().endswith(".json"):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(f"Pipeline config must be a mapping: {config_path}")
        loaded = _normalise_config_mapping(loaded)
        loaded = _apply_omegaconf_overrides(loaded, overrides)
    else:
        loaded = _load_hydra_config(config_path, overrides)

    PIPELINE_V2_CONFIG.update(loaded)
    return PIPELINE_V2_CONFIG


def get_pipeline_config_hash(config: Optional[Dict[str, Any]] = None) -> str:
    """Stable short hash for diagnostics and run-state records."""
    payload = json.dumps(config or PIPELINE_V2_CONFIG, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
