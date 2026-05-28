import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask

from visualization.routes import video_routes


def make_video_client(tmp_path):
    workspace = tmp_path / "workspace"
    uploads = workspace / "uploads"
    annotations = workspace / "annotations"
    nested = uploads / "nested"
    outside = tmp_path / "outside"
    nested.mkdir(parents=True)
    annotations.mkdir(parents=True)
    outside.mkdir()
    (uploads / "inside.mp4").write_bytes(b"inside video")
    (outside / "outside.mp4").write_bytes(b"outside video")

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
    return app.test_client(), workspace, uploads, nested, outside


def test_browse_files_rejects_paths_outside_workspace(tmp_path):
    client, _workspace, _uploads, _nested, outside = make_video_client(tmp_path)

    response = client.post("/api/browse-files", json={"path": str(outside)})

    assert response.status_code == 403
    assert response.get_json()["error"] == "Path is outside the allowed workspace"


def test_browse_files_limits_parent_and_returns_only_workspace_paths(tmp_path):
    client, workspace, uploads, nested, _outside = make_video_client(tmp_path)

    root_response = client.post("/api/browse-files", json={"path": str(workspace)})
    nested_response = client.post("/api/browse-files", json={"path": str(uploads)})

    assert root_response.status_code == 200
    assert root_response.get_json()["data"]["parent_path"] is None
    assert nested_response.status_code == 200
    data = nested_response.get_json()["data"]
    assert data["parent_path"] == str(workspace.resolve())
    assert any(directory["path"] == str(nested.resolve()) for directory in data["directories"])


def test_set_video_folder_rejects_paths_outside_workspace(tmp_path):
    client, _workspace, _uploads, _nested, outside = make_video_client(tmp_path)

    response = client.post("/api/set-video-folder", json={"folder_path": str(outside)})

    assert response.status_code == 403
    assert response.get_json()["error"] == "Path is outside the allowed workspace"


def test_external_video_serving_is_sandboxed_to_workspace(tmp_path):
    client, _workspace, uploads, _nested, outside = make_video_client(tmp_path)

    outside_response = client.get("/api/serve-video", query_string={"path": str(outside / "outside.mp4")})
    inside_response = client.get("/api/serve-video", query_string={"path": str(uploads / "inside.mp4")})

    assert outside_response.status_code == 403
    assert inside_response.status_code == 200
    assert inside_response.data == b"inside video"
