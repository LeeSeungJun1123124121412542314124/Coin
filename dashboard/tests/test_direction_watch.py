"""방향 전환 + 데이터 헬스 알림 테스트 — health dict 주입(순수 로직·상태 전이)."""

from __future__ import annotations

import pytest

from dashboard.backend.jobs.direction_watch import check_direction_and_health


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()  # 스키마(bot_state 포함)
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _health(status="ok", direction="long", ok=True, z=0.5):
    return {
        "status": status,
        "cache_age_hours": 2.0,
        "composite": {"direction": direction, "n_factors": 9, "composite_z": z, "ok": ok},
        "series": [],
    }


def test_first_run_no_alert(state_db):
    msgs = check_direction_and_health(_health(direction="long"))
    assert msgs == []  # 직전 상태 없음 → 알림 없이 저장만


def test_direction_flip_alert(state_db):
    check_direction_and_health(_health(direction="long"))           # 저장
    msgs = check_direction_and_health(_health(direction="short", z=-0.4))  # 전환
    assert len(msgs) == 1 and "방향 전환" in msgs[0]
    assert "강세" in msgs[0] and "약세" in msgs[0]


def test_same_direction_no_alert(state_db):
    check_direction_and_health(_health(direction="long"))
    msgs = check_direction_and_health(_health(direction="long"))
    assert msgs == []


def test_health_degradation_alert_once(state_db):
    check_direction_and_health(_health(status="ok"))                 # 정상 저장
    msgs = check_direction_and_health(_health(status="stale", ok=False))
    assert len(msgs) == 1 and "데이터 상태 경고" in msgs[0]
    # 연속 비정상 → 반복 안 함
    again = check_direction_and_health(_health(status="stale", ok=False))
    assert again == []


def test_no_direction_alert_when_unhealthy(state_db):
    """헬스 비정상(복합 ok=False)이면 방향 전환은 처리 안 함."""
    check_direction_and_health(_health(direction="long"))           # long 저장
    msgs = check_direction_and_health(_health(status="stale", direction="short", ok=False))
    # 헬스 경고는 나오지만 방향 전환은 없음
    assert any("데이터 상태 경고" in m for m in msgs)
    assert not any("방향 전환" in m for m in msgs)
