import sys
import types

import pytest
from pydantic import BaseModel

sys.modules.setdefault("ffmpeg", types.SimpleNamespace(Error=Exception))

from src.pipeline.common_utils import filter_causal_answer_evidence, preserve_fields_from_original
from src.pipeline.config import PIPELINE_V2_CONFIG, load_pipeline_v2_config
from src.pipeline.concurrent_inference import parse_structured_response, wrap_schema_with_confidence
from src.pipeline.prompts.handshake_verification import get_retriever_fulfillment_schema
from src.pipeline.prompts.video_chunk_retrieval import get_stage2_retrieval_schema


class ToyOutput(BaseModel):
    answer: int


def test_structured_response_validates_raw_schema():
    parsed, confidence = parse_structured_response('{"answer": 7}', ToyOutput)

    assert parsed == {"answer": 7}
    assert confidence is None


def test_structured_response_rejects_malformed_schema():
    with pytest.raises(Exception):
        parse_structured_response('{"answer": "not-an-int"}', ToyOutput)


def test_confidence_wrapped_response_unwraps_output():
    schema = wrap_schema_with_confidence(ToyOutput)
    parsed, confidence = parse_structured_response(
        '{"output": {"answer": 3}, "confidence_reasoning": "clear", "confidence_score": "High"}',
        schema,
        confidence_enabled=True,
        return_confidence_metadata=True,
    )

    assert parsed == {
        "answer": 3,
        "confidence_score": "High",
        "confidence_reasoning": "clear",
    }
    assert confidence == {"score": "High", "reasoning": "clear"}


def test_config_overrides_work_without_config_file():
    original = dict(PIPELINE_V2_CONFIG)
    try:
        loaded = load_pipeline_v2_config(
            overrides=["max_clip_duration=77", "max_video_clips_per_request=6"]
        )

        assert loaded["max_clip_duration"] == 77
        assert loaded["max_video_clips_per_request"] == 6
    finally:
        PIPELINE_V2_CONFIG.clear()
        PIPELINE_V2_CONFIG.update(original)


def test_hydra_yaml_config_loader_supports_flat_overrides(tmp_path):
    original = dict(PIPELINE_V2_CONFIG)
    config_path = tmp_path / "pipeline_v2.yaml"
    config_path.write_text(
        "\n".join([
            "defaults:",
            "  - _self_",
            "max_clip_duration: 111",
            "max_video_clips_per_request: 4",
        ]),
        encoding="utf-8",
    )

    try:
        loaded = load_pipeline_v2_config(
            str(config_path),
            overrides=["max_clip_duration=222"],
        )

        assert loaded["max_clip_duration"] == 222
        assert loaded["max_video_clips_per_request"] == 4
    finally:
        PIPELINE_V2_CONFIG.clear()
        PIPELINE_V2_CONFIG.update(original)


def test_retriever_schema_uses_configured_clip_duration(monkeypatch):
    monkeypatch.setitem(PIPELINE_V2_CONFIG, "max_clip_duration", 10)
    schema = get_stage2_retrieval_schema(
        ["vid_a"],
        video_meta={"vid_a": {"start_time": 1000.0, "duration": 60.0}},
    )

    parsed = schema.model_validate({
        "chunks": [{
            "relevance_reason": "Evidence check. Video duration: 01:00. Bounds valid.",
            "video_id": "vid_a",
            "start_time": "00:00",
            "end_time": "00:20",
            "relevance_score": 1.0,
        }]
    })

    assert parsed.chunks[0].end_time == "00:09.90"


def test_causal_filter_removes_future_evidence():
    qa = {
        "question": {
            "video_id": "vid_a",
            "time_spans": [{"video_id": "vid_a", "start_time": "00:10", "end_time": "00:12"}],
        },
        "answer": {
            "evidence_list": [
                {"video_id": "vid_a", "time_span": {"start_time": "00:01", "end_time": "00:03"}},
                {"video_id": "vid_a", "time_span": {"start_time": "00:20", "end_time": "00:21"}},
            ]
        },
    }

    removed = filter_causal_answer_evidence(qa, {"vid_a": 0.0}, 1000.0)

    assert removed == 1
    assert qa["answer"]["evidence_list"] == [
        {"video_id": "vid_a", "time_span": {"start_time": "00:01", "end_time": "00:03"}}
    ]


def test_handshake_retriever_schema_preserves_clip_purpose():
    schema = get_retriever_fulfillment_schema(["vid_a"])

    parsed = schema.model_validate({
        "fulfilled_clips": [{
            "video_id": "vid_a",
            "start_time": "00:01",
            "end_time": "00:05",
            "available": True,
            "relevance_note": "Shows the requested object.",
            "purpose": "evidence_verification",
        }],
        "caption_excerpts": [],
        "additional_context": "",
    })

    assert parsed.fulfilled_clips[0].purpose == "evidence_verification"


def test_preserve_fields_allows_explicit_skill_salvage_but_keeps_ids():
    original = {
        "question": {"question_reasoning": "original reason"},
        "answer": {"is_answerable": True, "answer_choices": [{"text": "A"}]},
        "metadata": {
            "qa_id": "qa_1",
            "original_idx": 4,
            "primary_video_id": "vid_a",
            "skill": "visual_recall",
        },
    }
    enhanced = {
        "question": {},
        "answer": {"is_answerable": False, "answer_choices": []},
        "metadata": {"skill": "conversational_memory"},
    }

    preserve_fields_from_original(
        enhanced,
        original,
        {"suggestions": ["SALVAGE: CHANGE SKILL TO conversational_memory."]},
    )

    assert enhanced["metadata"]["skill"] == "conversational_memory"
    assert enhanced["metadata"]["qa_id"] == "qa_1"
    assert enhanced["metadata"]["original_idx"] == 4
    assert enhanced["metadata"]["primary_video_id"] == "vid_a"
    assert enhanced["question"]["question_reasoning"] == "original reason"
    assert enhanced["answer"]["is_answerable"] is True
    assert enhanced["answer"]["answer_choices"] == [{"text": "A"}]
