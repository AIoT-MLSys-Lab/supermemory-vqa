import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask

from visualization import thumbnail_service
from visualization.routes import video_routes


def make_video_client(tmp_path):
    workspace = tmp_path / "workspace"
    uploads = workspace / "uploads"
    annotations = workspace / "annotations"
    uploads.mkdir(parents=True)
    annotations.mkdir(parents=True)
    (uploads / "video.mp4").write_bytes(b"video")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        UPLOAD_FOLDER=str(uploads),
        ANNOTATIONS_FOLDER=str(annotations),
        VIDEO_WORKSPACE_ROOTS=[str(workspace)],
        ALLOWED_EXTENSIONS={"mp4", "avi", "mov", "mkv", "webm"},
        ALLOWED_VRS_EXTENSIONS={"vrs"},
        RATELIMIT_ENABLED=False,
    )
    app.register_blueprint(video_routes.video_bp)
    return app.test_client(), uploads


def test_generate_all_thumbnails_uses_one_ffmpeg_process_and_maps_cache(tmp_path, monkeypatch):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    commands = []

    monkeypatch.setattr(thumbnail_service, "get_video_duration", lambda _path: 3.0)

    def fake_run(cmd, capture_output=True, timeout=None):
        commands.append(cmd)
        output_pattern = Path(cmd[-1])
        for index in range(3):
            (output_pattern.parent / f"frame_{index:05d}.jpg").write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(thumbnail_service.subprocess, "run", fake_run)

    generated = thumbnail_service.generate_all_thumbnails(str(video_path), interval=1.0)

    assert len(commands) == 1
    assert any("fps=1.0" in part for part in commands[0])
    assert [path.name for path in generated] == [
        "thumb_00000.jpg",
        "thumb_00001.jpg",
        "thumb_00002.jpg",
    ]
    assert all(path.exists() and path.read_bytes() == b"jpg" for path in generated)


def test_schedule_thumbnail_generation_dedupes_inflight_jobs(tmp_path, monkeypatch):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    submissions = []

    class FakeExecutor:
        def submit(self, fn, *args):
            submissions.append((fn, args))
            return object()

    monkeypatch.setattr(thumbnail_service, "get_cached_thumbnail", lambda _path, _bucket: None)
    monkeypatch.setattr(thumbnail_service, "_thumbnail_executor", FakeExecutor())

    with thumbnail_service._thumbnail_jobs_lock:
        thumbnail_service._thumbnail_jobs.clear()

    try:
        first = thumbnail_service.schedule_thumbnail_generation(str(video_path), 4)
        second = thumbnail_service.schedule_thumbnail_generation(str(video_path), 4)
    finally:
        with thumbnail_service._thumbnail_jobs_lock:
            thumbnail_service._thumbnail_jobs.clear()

    assert first is True
    assert second is False
    assert len(submissions) == 1


def test_thumbnail_route_returns_cached_jpeg(tmp_path, monkeypatch):
    client, uploads = make_video_client(tmp_path)
    thumb_path = uploads / "thumb_00003.jpg"
    thumb_path.write_bytes(b"jpeg")

    monkeypatch.setattr(video_routes, "get_cached_thumbnail", lambda _path, _bucket: thumb_path)

    response = client.get("/api/videos/thumbnail/video.mp4?t=3")

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"jpeg"


def test_thumbnail_route_cache_miss_enqueues_without_sync_generation(tmp_path, monkeypatch):
    client, _uploads = make_video_client(tmp_path)
    queued = []

    monkeypatch.setattr(video_routes, "get_cached_thumbnail", lambda _path, _bucket: None)

    def fake_schedule(video_path, timestamp_bucket):
        queued.append((video_path, timestamp_bucket))
        return True

    monkeypatch.setattr(video_routes, "schedule_thumbnail_generation", fake_schedule)

    response = client.get("/api/videos/thumbnail/video.mp4?t=8")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "code": "thumbnail_pending",
        "queued": True,
        "error": "Thumbnail is not cached yet",
    }
    assert len(queued) == 1
    assert queued[0][1] == 8
