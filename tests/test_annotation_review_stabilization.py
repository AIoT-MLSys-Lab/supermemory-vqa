import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask

from annotation import service as annotation_service_module
from annotation.service import VideoAnnotationService
from utils.validation import parse_timestamp, validate_timestamp
from visualization.routes import annotation_routes


def v2_document(revision=0):
    return {
        "video_id": "video",
        "metadata": {"revision": revision, "schema_version": "pipeline_v2"},
        "annotations": [
            {
                "question": {
                    "text": "Where is the mug?",
                    "room": "kitchen",
                    "modalities": ["Video"],
                    "video_id": "video",
                    "time_spans": [{"start_time": "00:01", "end_time": "00:03", "video_id": "video"}],
                    "question_reasoning": "The question is grounded.",
                },
                "answer": {
                    "text": "On the desk",
                    "is_answerable": True,
                    "balance_reasoning": "The distractors are plausible.",
                    "answer_choices": [
                        {"text": "On the desk", "choice_type": "correct", "explanation": "Visible."},
                        {"text": "Near the table", "choice_type": "vague", "explanation": "Too broad."},
                        {"text": "In the drawer", "choice_type": "incorrect", "explanation": "Not shown."},
                    ],
                    "evidence_list": [
                        {
                            "reason": "The mug appears on the desk.",
                            "room": "kitchen",
                            "video_id": "video",
                            "time_span": {"start_time": "00:02", "end_time": "00:03"},
                            "time_spans": [{"start_time": "00:02", "end_time": "00:03", "video_id": "video"}],
                            "modalities": ["Video"],
                            "extra_evidence_key": "keep me",
                        }
                    ],
                },
                "metadata": {
                    "qa_id": "qa-123",
                    "original_idx": 7,
                    "skill": "visual_recall",
                    "skill_reasoning": "This asks for visual memory.",
                    "primary_video_id": "video",
                    "confidence": 0.87,
                    "confidence_reasoning": "Clear evidence.",
                    "verification_score": {"from_metadata": True},
                    "extra_metadata_key": "keep me",
                },
                "verification_score": {"factual_correctness_score": 5},
                "human_review": {"status": "pending", "reviewed": False},
            }
        ],
    }


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_test_client(tmp_path):
    upload_dir = tmp_path / "videos"
    annotations_dir = tmp_path / "annotations"
    upload_dir.mkdir()
    annotations_dir.mkdir()
    (upload_dir / "video.mp4").write_bytes(b"")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        UPLOAD_FOLDER=str(upload_dir),
        ANNOTATIONS_FOLDER=str(annotations_dir),
        ALLOWED_EXTENSIONS={"mp4", "avi", "mov", "mkv", "webm"},
    )
    app.register_blueprint(annotation_routes.annotation_bp)
    return app.test_client(), upload_dir, annotations_dir


def test_v2_round_trip_preserves_metadata_answer_choices_and_rejection_reason():
    normalized = annotation_routes._normalise_v2_annotation_file(v2_document())["annotations"][0]

    assert normalized["annotation_id"] == "qa-123"
    assert normalized["metadata_details"]["qa_id"] == "qa-123"
    assert normalized["metadata_details"]["original_idx"] == 7
    assert normalized["metadata_details"]["skill_reasoning"] == "This asks for visual memory."
    assert normalized["metadata_details"]["primary_video_id"] == "video"
    assert normalized["verification_score"] == {"factual_correctness_score": 5}
    assert normalized["answer_choices"][0]["text"] == "On the desk"

    normalized["annotation_type"] = "rejected"
    normalized["rejection_reason"] = "Insufficient evidence"
    denormalized = annotation_routes._denormalise_v2_annotation(normalized)

    metadata = denormalized["qa_pair"]["metadata"]
    answer = denormalized["qa_pair"]["answer"]
    assert metadata["qa_id"] == "qa-123"
    assert metadata["original_idx"] == 7
    assert metadata["skill_reasoning"] == "This asks for visual memory."
    assert metadata["primary_video_id"] == "video"
    assert metadata["extra_metadata_key"] == "keep me"
    assert answer["answer_choices"][0]["choice_type"] == "correct"
    assert answer["balance_reasoning"] == "The distractors are plausible."
    assert answer["evidence_list"][0]["extra_evidence_key"] == "keep me"
    assert denormalized["rejection_reason"] == "Insufficient evidence"


def test_timestamp_validation_supports_hour_format():
    assert validate_timestamp("0:00")
    assert validate_timestamp("12:34")
    assert validate_timestamp("1:02:45")
    assert parse_timestamp("1:02:45") == 3765
    assert validate_timestamp("62:45")
    assert not validate_timestamp("1:62:45")
    assert not validate_timestamp("1:02:99")
    assert not validate_timestamp("1:2:03")


def test_json_save_writes_utf8_and_uses_atomic_replace(tmp_path, monkeypatch):
    output_path = tmp_path / "annotations.json"
    calls = []
    original_replace = annotation_service_module.os.replace

    def spy_replace(src, dst):
        calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr(annotation_service_module.os, "replace", spy_replace)

    VideoAnnotationService().save_annotations(
        {"annotations": [{"answer": "café"}], "metadata": {"revision": 0}},
        str(output_path),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "café" in content
    assert "\\u00e9" not in content
    assert calls and calls[0][1] == str(output_path)


def test_update_increments_revision_and_stale_revision_does_not_write(tmp_path):
    client, upload_dir, _annotations_dir = make_test_client(tmp_path)
    annotation_path = upload_dir / "video_verified_annotations.json"
    write_json(annotation_path, v2_document(revision=0))

    queue = client.get("/api/qa-review").get_json()
    item = queue["items"][0]
    assert item["source"]["file_revision"] == 0
    assert item["annotation"]["annotation_id"] == "qa-123"

    payload = item["annotation"]
    payload["human_review"] = {"status": "accepted", "reviewed": True}
    payload["_source"] = {"file_revision": 0, "annotation_id": "qa-123"}
    response = client.put(
        "/api/annotations/video.mp4/video_verified_annotations.json/0",
        json=payload,
    )

    assert response.status_code == 200
    saved = response.get_json()
    assert saved["success"] is True
    assert saved["annotation_id"] == "qa-123"
    assert saved["file_revision"] == 1
    assert read_json(annotation_path)["metadata"]["revision"] == 1

    stale_payload = item["annotation"]
    stale_payload["human_review"] = {"status": "rejected", "reviewed": True}
    stale_payload["_source"] = {"file_revision": 0, "annotation_id": "qa-123"}
    stale_response = client.put(
        "/api/annotations/video.mp4/video_verified_annotations.json/0",
        json=stale_payload,
    )

    assert stale_response.status_code == 409
    conflict = stale_response.get_json()
    assert conflict["code"] == "conflict"
    assert conflict["file_revision"] == 1
    assert read_json(annotation_path)["metadata"]["revision"] == 1
    current_review = read_json(annotation_path)["annotations"][0]["human_review"]
    assert current_review["status"] == "accepted"


def test_mismatched_annotation_id_and_invalid_timestamp_do_not_write(tmp_path):
    client, upload_dir, _annotations_dir = make_test_client(tmp_path)
    annotation_path = upload_dir / "video_verified_annotations.json"
    write_json(annotation_path, v2_document(revision=3))

    item = client.get("/api/qa-review").get_json()["items"][0]

    wrong_id_payload = item["annotation"]
    wrong_id_payload["_source"] = {"file_revision": 3, "annotation_id": "wrong-id"}
    wrong_id_response = client.put(
        "/api/annotations/video.mp4/video_verified_annotations.json/0",
        json=wrong_id_payload,
    )
    assert wrong_id_response.status_code == 409
    assert read_json(annotation_path)["metadata"]["revision"] == 3

    invalid_payload = item["annotation"]
    invalid_payload["question_time_spans"][0]["start"] = "00:09"
    invalid_payload["question_time_spans"][0]["end"] = "00:01"
    invalid_payload["_source"] = {"file_revision": 3, "annotation_id": "qa-123"}
    invalid_response = client.put(
        "/api/annotations/video.mp4/video_verified_annotations.json/0",
        json=invalid_payload,
    )

    assert invalid_response.status_code == 400
    assert invalid_response.get_json()["code"] == "validation_error"
    assert read_json(annotation_path)["metadata"]["revision"] == 3


def test_add_and_delete_increment_revision_for_legacy_file(tmp_path):
    client, upload_dir, _annotations_dir = make_test_client(tmp_path)
    annotation_path = upload_dir / "video_annotations_manual.json"
    write_json(annotation_path, {"annotations": [], "metadata": {"revision": 0}})

    annotation = {
        "annotation_id": "legacy-1",
        "video_filename": "video.mp4",
        "question": "What is visible?",
        "answer": "A mug",
        "time_span": {"start": "00:01", "end": "00:02"},
        "location": None,
        "room": "kitchen",
        "modalities": ["Video"],
        "skill": "visual_recall",
    }
    add_response = client.post(
        "/api/annotations/video.mp4/video_annotations_manual.json/add",
        json=annotation,
    )
    assert add_response.status_code == 200
    assert add_response.get_json()["file_revision"] == 1
    assert read_json(annotation_path)["metadata"]["revision"] == 1

    delete_response = client.delete("/api/annotations/video.mp4/video_annotations_manual.json/0")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["file_revision"] == 2
    assert read_json(annotation_path)["metadata"]["revision"] == 2
