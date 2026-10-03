from __future__ import annotations

from fastapi.testclient import TestClient

from distillery.app import app

client = TestClient(app)


def test_delete_rejects_traversal(datasets_root):
    (datasets_root.parent / "keep").mkdir()
    for sid in ("%2e%2e", "%2e"):
        r = client.delete(f"/api/distill/{sid}")
        assert r.status_code == 400
    assert (datasets_root.parent / "keep").is_dir()
    assert datasets_root.is_dir()


def test_delete_unknown_session_is_404():
    assert client.delete("/api/distill/abc123").status_code == 404


def test_no_cors_for_other_origins():
    r = client.get("/api/distill/sessions", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
