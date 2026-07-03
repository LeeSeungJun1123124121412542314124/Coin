"""TGA 급변 이벤트 알림 — 상태머신 전이·중복방지·히스테리시스 복구·방향전환 (delta 주입)."""

from __future__ import annotations

import pytest

from dashboard.backend.jobs.direction_watch import check_tga_event

T = 120_000  # 임계 (백만$) — _TGA_THRESHOLD와 동일, 0.7T=84,000


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()  # 스키마(bot_state, alert_history)
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _alerts(connection):
    with connection.get_db() as conn:
        return conn.execute(
            "SELECT symbol, alert_level FROM alert_history WHERE alert_level = 'MACRO_EVENT'"
        ).fetchall()


def test_below_threshold_no_alert(state_db):
    assert check_tga_event(50_000) == []
    assert len(_alerts(state_db)) == 0


def test_positive_cross_fires_and_records(state_db):
    msgs = check_tga_event(150_000)
    assert len(msgs) == 1 and "급증" in msgs[0]
    rows = _alerts(state_db)
    assert len(rows) == 1 and rows[0]["symbol"] == "TGA"


def test_no_duplicate_while_sustained(state_db):
    check_tga_event(150_000)
    assert check_tga_event(160_000) == []      # 여전히 above_positive → 무발화
    assert len(_alerts(state_db)) == 1


def test_reset_below_hysteresis_then_refire(state_db):
    check_tga_event(150_000)                    # 발화
    assert check_tga_event(50_000) == []        # |Δ|<0.7T=84k → 리셋(무발화)
    msgs = check_tga_event(150_000)             # 재 stale → 재발화
    assert len(msgs) == 1
    assert len(_alerts(state_db)) == 2


def test_direction_flip_refires_without_reset(state_db):
    check_tga_event(150_000)                    # 증가 발화
    msgs = check_tga_event(-150_000)            # 0.7T 복귀 없이 감소 → 방향전환 재발화
    assert len(msgs) == 1 and "급감" in msgs[0]
    assert len(_alerts(state_db)) == 2
