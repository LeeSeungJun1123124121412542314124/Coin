"""리서치 분석 일별 스냅샷과 어제·7일 전 비교값 (docs/plans/research-compare-spec-2026-11-24.md)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import json
import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema

TODAY = date(2026, 11, 24)


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


@contextmanager
def _fake_db(conn):
    yield conn


@pytest.fixture
def conn(monkeypatch):
    from dashboard.backend.db import connection

    c = _memory_conn()
    monkeypatch.setattr(connection, "get_db", lambda: _fake_db(c))
    return c


def _category(key: str, score: int, level: str = "neutral", summary: str = "요약") -> dict:
    return {
        "key": key,
        "name": key,
        "level": level,
        "score": score,
        "title": f"{key} {score}/100",
        "summary": summary,
        "details": {"x": 1},
        "updated_at": "2026-11-24T00:00:00+00:00",
    }


def _rows(conn) -> list[tuple]:
    return [
        tuple(r)
        for r in conn.execute("SELECT date, key, level, score, summary FROM research_snapshot ORDER BY date, key")
    ]


def test_save_snapshot_keeps_one_row_per_day_and_overwrites_same_day(conn) -> None:
    from dashboard.backend.services import research_history

    assert research_history.save_snapshot([_category("onchain", 38), _category("macro", 40)], TODAY) == 2
    assert research_history.save_snapshot([_category("onchain", 42, "bearish", "나중 값")], TODAY) == 1

    assert _rows(conn) == [
        ("2026-11-24", "macro", "neutral", 40, "요약"),
        ("2026-11-24", "onchain", "bearish", 42, "나중 값"),
    ]


def test_save_snapshot_skips_placeholder_categories(conn) -> None:
    """오류·적재 중 상태는 실제 분석 결과가 아니므로 저장하지 않는다."""
    from dashboard.backend.services import research_analyzer, research_history

    placeholder = research_analyzer._error_category("whale", "기타")
    assert placeholder["placeholder"] is True

    saved = research_history.save_snapshot([_category("onchain", 38), placeholder], TODAY)

    assert saved == 1
    assert [r[1] for r in _rows(conn)] == ["onchain"]


def test_load_comparisons_picks_latest_before_today_and_week_window(conn) -> None:
    from dashboard.backend.services import research_history

    for days_ago, score in [(0, 42), (1, 38), (6, 36), (7, 35), (14, 30), (15, 29)]:
        research_history.save_snapshot(
            [_category("onchain", score, summary=f"{days_ago}일 전 요약")], TODAY - timedelta(days=days_ago)
        )

    compare = research_history.load_comparisons(TODAY)["onchain"]

    # 오늘 저장분은 비교 대상이 아니다 — 어제(1일 전)가 가장 최근
    assert compare["prev"] == {
        "date": "2026-11-23", "days_ago": 1, "score": 38, "level": "neutral", "summary": "1일 전 요약",
    }
    # 7일 전 이전의 가장 최근 — 6일 전은 제외, 7일 전이 선택된다
    assert compare["week"] == {"date": "2026-11-17", "days_ago": 7, "score": 35, "level": "neutral"}


def test_load_comparisons_week_falls_back_within_14_days_only(conn) -> None:
    from dashboard.backend.services import research_history

    # 주말 등으로 7일 전 저장분이 없으면 그보다 앞선 가장 최근 것 — 단 14일 이내
    research_history.save_snapshot([_category("macro", 30)], TODAY - timedelta(days=9))
    research_history.save_snapshot([_category("whale", 50)], TODAY - timedelta(days=15))

    comparisons = research_history.load_comparisons(TODAY)

    assert comparisons["macro"]["week"]["days_ago"] == 9
    # prev는 "오늘 이전 가장 최근"이라 9일 전 것이 그대로 쓰인다
    assert comparisons["macro"]["prev"]["days_ago"] == 9
    assert comparisons["whale"]["week"] is None
    assert comparisons["whale"]["prev"]["days_ago"] == 15


def test_attach_comparisons_adds_compare_without_mutating_input(conn) -> None:
    from dashboard.backend.services import research_history

    research_history.save_snapshot([_category("onchain", 38)], TODAY - timedelta(days=1))
    onchain, macro = _category("onchain", 42), _category("macro", 40)
    result = {"generated_at": "t", "categories": [onchain, macro]}
    snapshot = json.dumps(result, ensure_ascii=False)

    attached = research_history.attach_comparisons(result, TODAY)

    assert attached["generated_at"] == "t"
    assert attached["categories"][0]["compare"]["prev"]["score"] == 38
    assert attached["categories"][0]["compare"]["week"] is None
    # 저장분이 전혀 없는 항목도 같은 모양으로 내려준다
    assert attached["categories"][1]["compare"] == {"prev": None, "week": None}
    # analyze_all 결과는 캐시된 객체일 수 있다 — 원본은 건드리지 않는다
    assert json.dumps(result, ensure_ascii=False) == snapshot
    assert "compare" not in onchain


def test_attach_comparisons_gives_no_compare_to_placeholder_cards(conn) -> None:
    """오류·적재 중 카드는 점수가 0으로 채워져 있어 '어제 38 → 오늘 0'처럼 오해를 준다 — 비교를 붙이지 않는다."""
    from dashboard.backend.services import research_analyzer, research_history

    research_history.save_snapshot([_category("whale", 50)], TODAY - timedelta(days=1))
    result = {"generated_at": "t", "categories": [research_analyzer._error_category("whale", "기타")]}

    attached = research_history.attach_comparisons(result, TODAY)

    assert attached["categories"][0]["compare"] == {"prev": None, "week": None}


@pytest.mark.asyncio
async def test_snapshot_job_saves_todays_analysis(conn, monkeypatch) -> None:
    from dashboard.backend.jobs import snapshot_research as job
    from dashboard.backend.services import research_history

    async def fake_analyze_all() -> dict:
        return {"generated_at": "t", "categories": [_category("onchain", 42), _category("macro", 40)]}

    monkeypatch.setattr(job, "analyze_all", fake_analyze_all)
    monkeypatch.setattr(research_history, "kst_today", lambda: TODAY)

    await job.snapshot_research()

    assert [(r[0], r[1], r[3]) for r in _rows(conn)] == [
        ("2026-11-24", "macro", 40),
        ("2026-11-24", "onchain", 42),
    ]


@pytest.mark.asyncio
async def test_route_returns_plain_result_when_comparison_lookup_fails(monkeypatch) -> None:
    """비교값 조회가 실패해도 리서치 화면 응답은 그대로 나가야 한다."""
    from dashboard.backend.api import research_routes

    async def fake_analyze_all() -> dict:
        return {"generated_at": "t", "categories": [_category("onchain", 42)]}

    def broken(result, day):
        raise sqlite3.OperationalError("no such table: research_snapshot")

    monkeypatch.setattr(research_routes, "analyze_all", fake_analyze_all)
    monkeypatch.setattr(research_routes, "attach_comparisons", broken)

    response = await research_routes.get_research_analysis()

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["categories"][0]["score"] == 42
    assert "compare" not in body["categories"][0]


@pytest.mark.asyncio
async def test_route_attaches_comparisons(conn, monkeypatch) -> None:
    from dashboard.backend.api import research_routes
    from dashboard.backend.services import research_history

    research_history.save_snapshot([_category("onchain", 38)], TODAY - timedelta(days=1))

    async def fake_analyze_all() -> dict:
        return {"generated_at": "t", "categories": [_category("onchain", 42)]}

    monkeypatch.setattr(research_routes, "analyze_all", fake_analyze_all)
    monkeypatch.setattr(research_routes, "kst_today", lambda: TODAY)

    response = await research_routes.get_research_analysis()

    body = json.loads(response.body)
    assert body["categories"][0]["compare"]["prev"]["score"] == 38
