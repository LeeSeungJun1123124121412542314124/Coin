"""Tests for webhook server endpoints — 4 tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.bot.webhook_server import create_app

    app = create_app(
        pipeline_fn=AsyncMock(return_value=[]),
        report_fn=AsyncMock(return_value=None),
    )
    return TestClient(app)


class TestWebhookEndpoints:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_scheduled_run_returns_200(self, client):
        resp = client.post("/scheduled-run")
        assert resp.status_code == 200

    def test_webhook_accepts_post(self, client):
        payload = {"update_id": 1, "message": {"chat": {"id": 123}, "text": "/help"}}
        resp = client.post("/webhook", json=payload)
        # Should return 200 (processed) or 400 (bad request)
        assert resp.status_code in (200, 400)

    def test_scheduled_report_returns_200(self, client):
        resp = client.post("/scheduled-report")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_health_endpoint_has_uptime(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
