"""반도체 정점 카드 stale 알림 테스트 — 순수 판정 + bot_state 전이·중복방지·복구."""

from __future__ import annotations

from datetime import date

import pytest

from dashboard.backend.jobs.direction_watch import check_semiconductor_stale, prepare_semiconductor_stale
from dashboard.backend.services.research_analyzer import (
    SEMICONDUCTOR_SIGNALS_AS_OF,
    semiconductor_stale_status,
)


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()  # 스키마(bot_state, alert_history 포함)
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _as_of_plus(days: int) -> date:
    y, m, d = (int(x) for x in SEMICONDUCTOR_SIGNALS_AS_OF.split("-"))
    from datetime import timedelta
    return date(y, m, d) + timedelta(days=days)


def _status(is_stale: bool, days_since: int = 22) -> dict:
    return {
        "as_of": SEMICONDUCTOR_SIGNALS_AS_OF,
        "days_since": days_since,
        "threshold_days": 21,
        "is_stale": is_stale,
        "peak_count": 5,
        "total": 9,
        "level": "critical",
    }


def _alert_rows(connection):
    with connection.get_db() as conn:
        return conn.execute(
            "SELECT symbol, alert_level FROM alert_history WHERE alert_level = 'STALE_SIGNAL'"
        ).fetchall()


# ── 순수 판정 ─────────────────────────────────────────────

def test_status_not_stale_at_threshold():
    """21일 경계 — 초과가 아니므로 stale 아님."""
    s = semiconductor_stale_status(today=_as_of_plus(21))
    assert s["days_since"] == 21
    assert s["threshold_days"] == 21
    assert s["is_stale"] is False


def test_status_stale_past_threshold():
    """22일 — 임계 초과로 stale."""
    s = semiconductor_stale_status(today=_as_of_plus(22))
    assert s["days_since"] == 22
    assert s["is_stale"] is True
    assert s["total"] == 9
    assert s["level"] in {"bullish", "neutral", "warning", "critical"}


# ── 전이·중복방지·복구 ─────────────────────────────────────

def test_stale_fires_once_and_records_history(state_db):
    msgs = check_semiconductor_stale(_status(is_stale=True))
    assert len(msgs) == 1 and "갱신 필요" in msgs[0]
    rows = _alert_rows(state_db)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "반도체"


def test_stale_no_duplicate_on_rerun(state_db):
    check_semiconductor_stale(_status(is_stale=True))
    again = check_semiconductor_stale(_status(is_stale=True))
    assert again == []
    assert len(_alert_rows(state_db)) == 1  # 중복 INSERT 없음


def test_recovery_resets_and_refires(state_db):
    check_semiconductor_stale(_status(is_stale=True))       # 1회 발송
    check_semiconductor_stale(_status(is_stale=False))      # 복구 → 리셋
    msgs = check_semiconductor_stale(_status(is_stale=True))  # 재 stale → 재발송
    assert len(msgs) == 1
    assert len(_alert_rows(state_db)) == 2


def test_prepare_stale_does_not_record_before_commit(state_db):
    actions = prepare_semiconductor_stale(_status(is_stale=True))
    assert len(actions) == 1
    assert actions[0].message and "갱신 필요" in actions[0].message
    assert len(_alert_rows(state_db)) == 0

    actions[0].commit()
    assert len(_alert_rows(state_db)) == 1
