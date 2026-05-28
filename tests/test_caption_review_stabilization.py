import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask

from visualization.routes import caption_routes


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_caption_client(tmp_path):
    upload_dir = tmp_path / "videos"
    upload_dir.mkdir()
    (upload_dir / "video.mp4").write_bytes(b"")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        UPLOAD_FOLDER=str(upload_dir),
        ALLOWED_EXTENSIONS={"mp4", "avi", "mov", "mkv", "webm"},
    )
    app.register_blueprint(caption_routes.caption_bp)
    return app.test_client(), upload_dir


def caption_document(revision=0):
    return {
        "caption_type": "narration",
        "captions": [
            {
                "text": "User picks up a mug.",
                "start": "0:01",
                "end": "0:03",
                "importance": "medium",
                "confidence": "high",
            }
        ],
        "human_review": {"status": "pending"},
        "metadata": {"revision": revision, "video_filename": "video.mp4"},
    }


def test_caption_detail_includes_file_revision_and_update_increments(tmp_path):
    client, upload_dir = make_caption_client(tmp_path)
    caption_path = upload_dir / "video_captions_narration.json"
    write_json(caption_path, caption_document(revision=0))

    detail = client.get("/api/captions/video.mp4/video_captions_narration.json").get_json()
    assert detail["source"]["file_revision"] == 0

    captions = detail["captions"]
    captions[0]["text"] = "User picks up a café mug."
    response = client.put(
        "/api/captions/video.mp4/video_captions_narration.json",
        json={"captions": captions, "_source": {"file_revision": 0}},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["file_revision"] == 1
    assert payload["data"]["source"]["file_revision"] == 1
    saved = caption_path.read_text(encoding="utf-8")
    assert "café" in saved
    assert "\\u00e9" not in saved
    assert read_json(caption_path)["metadata"]["revision"] == 1


def test_caption_stale_revision_returns_conflict_without_writing(tmp_path):
    client, upload_dir = make_caption_client(tmp_path)
    caption_path = upload_dir / "video_captions_narration.json"
    write_json(caption_path, caption_document(revision=0))

    detail = client.get("/api/captions/video.mp4/video_captions_narration.json").get_json()
    captions = detail["captions"]
    captions[0]["text"] = "First save"
    first = client.put(
        "/api/captions/video.mp4/video_captions_narration.json",
        json={"captions": captions, "_source": {"file_revision": 0}},
    )
    assert first.status_code == 200

    stale_captions = detail["captions"]
    stale_captions[0]["text"] = "Stale save"
    stale = client.put(
        "/api/captions/video.mp4/video_captions_narration.json",
        json={"captions": stale_captions, "_source": {"file_revision": 0}},
    )

    assert stale.status_code == 409
    payload = stale.get_json()
    assert payload["code"] == "conflict"
    assert payload["file_revision"] == 1
    saved = read_json(caption_path)
    assert saved["metadata"]["revision"] == 1
    assert saved["captions"][0]["text"] == "First save"


def test_caption_invalid_timestamp_range_does_not_write(tmp_path):
    client, upload_dir = make_caption_client(tmp_path)
    caption_path = upload_dir / "video_captions_narration.json"
    write_json(caption_path, caption_document(revision=3))

    captions = caption_document(revision=3)["captions"]
    captions[0]["start"] = "0:09"
    captions[0]["end"] = "0:01"
    response = client.put(
        "/api/captions/video.mp4/video_captions_narration.json",
        json={"captions": captions, "_source": {"file_revision": 3}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "validation_error"
    assert "Caption 1 start must be before or equal to end" in payload["details"]
    assert read_json(caption_path)["metadata"]["revision"] == 3


def test_caption_update_requires_file_revision(tmp_path):
    client, upload_dir = make_caption_client(tmp_path)
    caption_path = upload_dir / "video_captions_narration.json"
    write_json(caption_path, caption_document(revision=0))

    response = client.put(
        "/api/captions/video.mp4/video_captions_narration.json",
        json={"captions": caption_document()["captions"]},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_error"
    assert read_json(caption_path)["metadata"]["revision"] == 0
