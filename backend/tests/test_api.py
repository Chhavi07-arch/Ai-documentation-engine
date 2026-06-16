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
