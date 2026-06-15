"""Tests for the GitHub webhook endpoint's authentication and routing.

These cover signature verification and event/branch routing without performing
any real git operations (those are exercised by change-detection tests).
"""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_disabled_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    res = client.post(
        "/api/github/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "push"},
    )
    assert res.status_code == 503


def test_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "s3cr3t")
    res = client.post(
        "/api/github/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert res.status_code == 401


def test_webhook_ping_with_valid_signature(monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setattr(settings, "github_webhook_secret", secret)
    body = b'{"zen": "Keep it simple."}'
    res = client.post(
        "/api/github/webhook",
        content=body,
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": _sign(secret, body)},
    )
    assert res.status_code == 200
    assert res.json()["event"] == "ping"


def test_webhook_untracked_repo_is_ignored(monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setattr(settings, "github_webhook_secret", secret)
    body = json.dumps(
        {"ref": "refs/heads/main", "repository": {"full_name": "nobody/does-not-exist"}}
    ).encode()
    res = client.post(
        "/api/github/webhook",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(secret, body)},
    )
    assert res.status_code == 200
    assert "ignored" in res.json()
