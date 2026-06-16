"""Smoke tests for the HTTP API surface."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_config_shape():
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert "ai_enabled" in body and "model" in body


def test_stats_shape():
    res = client.get("/api/stats")
    assert res.status_code == 200
    assert "documentation_coverage" in res.json()


def test_ingest_rejects_invalid_url():
    res = client.post("/api/repositories/ingest", json={"url": "not-a-url"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"


def test_missing_repository_returns_404():
    res = client.get("/api/repositories/999999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_export_missing_doc_returns_404():
    res = client.get("/api/docs/999999/export")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_webhook_ping():
    res = client.post(
        "/api/webhooks/github", json={"zen": "hi"}, headers={"X-GitHub-Event": "ping"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pong"


def test_webhook_unknown_repo_returns_404():
    res = client.post(
        "/api/webhooks/github",
        json={"repository": {"full_name": "nobody/nothing"}},
        headers={"X-GitHub-Event": "push"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_webhook_queues_detection_for_known_repo():
    from app.core.database import SessionLocal
    from app.models import Repository
    from app.models.enums import RepositoryStatus

    db = SessionLocal()
    repo = Repository(
        name="repo",
        full_name="hook/repo",
        url="https://github.com/hook/repo",
        local_path="",
        status=RepositoryStatus.READY.value,
    )
    db.add(repo)
    db.commit()
    rid = repo.id
    db.close()

    res = client.post(
        "/api/webhooks/github",
        json={"repository": {"full_name": "hook/repo"}},
        headers={"X-GitHub-Event": "push"},
    )
    assert res.status_code == 202
    assert rid in res.json()["repositories_queued"]
