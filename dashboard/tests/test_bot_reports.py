"""그록봇 리포트 수신·조회 (docs/plans/bot-reports-spec-2026-11-24.md)."""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from dashboard.backend.db.connection import _init_schema

KEY = "test-bot-key-0123456789"


@pytest.fixture
def conn(monkeypatch):
    from dashboard.backend.db import connection

    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    _init_schema(c)

    @contextmanager
    def fake_get_db():
        yield c

    monkeypatch.setattr(connection, "get_db", fake_get_db)
    return c


@pytest.fixture
def client(conn, monkeypatch):
    from dashboard.backend.api import bot_report_routes

    monkeypatch.setenv("BOT_INGEST_KEY", KEY)
    bot_report_routes.limiter.reset()
    app = FastAPI()
    app.state.limiter = bot_report_routes.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(bot_report_routes.ingest_router, prefix="/api")
    app.include_router(bot_report_routes.router, prefix="/api")
    return TestClient(app)


def _report(**over) -> dict:
    return {
        "kind": "heatmap",
        "title": "CoinGlass 청산 히트맵 · 11/22 09:17 KST",
        "body": "| 구분 | 11/21 | 11/22 |\n|---|---|---|\n| 현재가 | $58,970 | $60,270 |",
        "reported_at": "2026-11-22T00:17:00+00:00",
        **over,
    }


def test_ingest_requires_matching_bot_key(client) -> None:
    assert client.post("/api/bot-reports", json=_report()).status_code == 401
    assert client.post("/api/bot-reports", json=_report(), headers={"X-Bot-Key": "wrong"}).status_code == 401

    ok = client.post("/api/bot-reports", json=_report(), headers={"X-Bot-Key": KEY})

    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["duplicate"] is False


def test_ingest_is_disabled_until_key_is_configured(client, monkeypatch) -> None:
    """키를 등록하기 전에는 어떤 값으로도 받지 않는다 — 빈 키와 빈 헤더가 일치해 통과하면 안 된다."""
    monkeypatch.delenv("BOT_INGEST_KEY")

    assert client.post("/api/bot-reports", json=_report(), headers={"X-Bot-Key": ""}).status_code == 503
    assert client.post("/api/bot-reports", json=_report(), headers={"X-Bot-Key": KEY}).status_code == 503


@pytest.mark.parametrize("bad", [
    {"kind": "unknown"},
    {"title": ""},
    {"title": "가" * 201},
    {"body": ""},
    {"body": "가" * 20001},
    {"reported_at": "어제"},
    {"data": "객체가 아님"},
])
def test_ingest_rejects_invalid_payload(client, bad) -> None:
    resp = client.post("/api/bot-reports", json=_report(**bad), headers={"X-Bot-Key": KEY})

    assert resp.status_code == 422


def test_ingest_stores_report_and_ignores_exact_resend(client, conn) -> None:
    headers = {"X-Bot-Key": KEY}
    first = client.post("/api/bot-reports", json=_report(data={"long_pct": 30}), headers=headers).json()
    again = client.post("/api/bot-reports", json=_report(data={"long_pct": 30}), headers=headers).json()
    other = client.post("/api/bot-reports", json=_report(title="다른 제목"), headers=headers).json()

    assert again == {"ok": True, "id": first["id"], "duplicate": True}
    assert other["id"] != first["id"]
    rows = conn.execute("SELECT kind, title, data_json, reported_at FROM bot_reports ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["kind"] == "heatmap"
    assert rows[0]["data_json"] == '{"long_pct": 30}'
    assert rows[0]["reported_at"] == "2026-11-22T00:17:00+00:00"


def test_ingest_defaults_reported_at_to_receive_time(client, conn) -> None:
    payload = _report()
    del payload["reported_at"]

    client.post("/api/bot-reports", json=payload, headers={"X-Bot-Key": KEY})

    row = conn.execute("SELECT reported_at, received_at FROM bot_reports").fetchone()
    assert row["reported_at"] == row["received_at"]


def test_list_returns_newest_first_with_kind_filter_and_limit(client) -> None:
    headers = {"X-Bot-Key": KEY}
    for i, kind in enumerate(["daily_check", "heatmap", "whale", "heatmap"]):
        client.post(
            "/api/bot-reports",
            json=_report(kind=kind, title=f"리포트 {i}", reported_at=f"2026-11-2{i}T00:00:00+00:00"),
            headers=headers,
        )

    all_reports = client.get("/api/bot-reports").json()["reports"]
    heatmaps = client.get("/api/bot-reports", params={"kind": "heatmap"}).json()["reports"]
    limited = client.get("/api/bot-reports", params={"limit": 1}).json()["reports"]

    assert [r["title"] for r in all_reports] == ["리포트 3", "리포트 2", "리포트 1", "리포트 0"]
    assert [r["title"] for r in heatmaps] == ["리포트 3", "리포트 1"]
    assert [r["title"] for r in limited] == ["리포트 3"]
    assert set(all_reports[0]) == {"id", "kind", "title", "body", "data", "reported_at", "received_at"}


def test_list_rejects_unknown_kind(client) -> None:
    assert client.get("/api/bot-reports", params={"kind": "unknown"}).status_code == 422


def test_ingest_is_rate_limited_per_ip(client) -> None:
    headers = {"X-Bot-Key": KEY}
    codes = [
        client.post("/api/bot-reports", json=_report(title=f"연속 {i}"), headers=headers).status_code
        for i in range(31)
    ]

    assert codes[:30] == [200] * 30
    assert codes[30] == 429


def test_routers_are_registered_with_right_auth() -> None:
    """수신은 PIN 없이(봇 키로), 조회는 다른 화면처럼 PIN 토큰으로 — main.py 등록을 확인한다."""
    from pathlib import Path

    source = Path("dashboard/backend/main.py").read_text(encoding="utf-8")

    assert 'app.include_router(bot_report_ingest_router, prefix="/api")' in source
    assert 'app.include_router(bot_report_router, prefix="/api", dependencies=_auth_dep)' in source
