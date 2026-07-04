"""SPF 복합 모델 교체 테스트 — composite_prediction(순수) + 다horizon 판정(DB)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dashboard.backend.services.spf_service import (
    EXPECTED_ACCURACY,
    PRED_HORIZONS,
    composite_prediction,
)


# ── composite_prediction (순수, 덕타이핑) ────────────────────
def test_composite_prediction_long():
    p = composite_prediction(SimpleNamespace(direction="long", confidence=60.0, composite_z=0.6))
    assert p["direction"] == "상승" and p["up_prob"] > p["down_prob"] and p["confidence"] == 60


def test_composite_prediction_short():
    p = composite_prediction(SimpleNamespace(direction="short", confidence=40.0, composite_z=-0.4))
    assert p["direction"] == "하락" and p["down_prob"] > p["up_prob"]


def test_composite_prediction_neutral_low_confidence():
    """중립은 50:50 + 낮은 신뢰도 (구 85 버그 해소)."""
    p = composite_prediction(SimpleNamespace(direction="neutral", confidence=8.0, composite_z=0.05))
    assert p["direction"] == "중립" and p["up_prob"] == 50 and p["confidence"] != 85 and p["confidence"] == 8


def test_composite_prediction_none_fallback():
    p = composite_prediction(None)
    assert p["direction"] == "중립" and p["confidence"] == 0


def test_expected_accuracy_constants():
    assert set(PRED_HORIZONS) == {7, 14, 30, 60}
    assert EXPECTED_ACCURACY == {7: 49.8, 14: 54.3, 30: 59.2, 60: 64.9}


# ── 다horizon 판정 (DB) ──────────────────────────────────────
@pytest.fixture
def spf_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "spf.db"))
    monkeypatch.setattr(connection, "_conn", None)
    conn = connection.get_connection()  # 스키마 + 마이그레이션(result_7d 등)
    yield conn
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _seed(conn, direction, price_then):
    conn.execute("INSERT INTO spf_records (date, price) VALUES ('2026-01-01', ?)", (price_then,))
    conn.execute("INSERT INTO predictions (date, direction) VALUES ('2026-01-01', ?)", (direction,))
    conn.commit()


def _judge(conn, price_now):
    from datetime import date
    from dashboard.backend.jobs.update_predictions import _judge_horizon
    _judge_horizon(conn, date(2026, 1, 1), price_now, "result_7d")
    return conn.execute("SELECT result_7d FROM predictions WHERE date='2026-01-01'").fetchone()["result_7d"]


def _judge_col(conn, price_now, col):
    from datetime import date
    from dashboard.backend.jobs.update_predictions import _judge_horizon
    _judge_horizon(conn, date(2026, 1, 1), price_now, col)
    return conn.execute(f"SELECT {col} FROM predictions WHERE date='2026-01-01'").fetchone()[col]


def test_judge_up_hit(spf_db):
    _seed(spf_db, "상승", 100.0)
    assert _judge(spf_db, 105.0) == "hit"   # +5% > +1%


def test_judge_up_miss(spf_db):
    _seed(spf_db, "상승", 100.0)
    assert _judge(spf_db, 100.5) == "miss"  # +0.5% 미달


def test_judge_down_hit(spf_db):
    _seed(spf_db, "하락", 100.0)
    assert _judge(spf_db, 95.0) == "hit"    # -5% < -1%


def test_judge_neutral_recorded_not_hitmiss(spf_db):
    _seed(spf_db, "중립", 100.0)
    assert _judge(spf_db, 130.0) == "neutral"  # 중립은 hit/miss 아님


def test_judge_missing_price_logs_warning(spf_db, caplog):
    """예측일 가격 없어 영구 미판정되는 경우 경고 로깅(조용한 스킵 방지)."""
    import logging
    _seed(spf_db, "상승", None)  # price NULL → 판정 불가
    with caplog.at_level(logging.WARNING):
        result = _judge(spf_db, 105.0)
    assert result is None  # 판정 안 됨(기존 동작 유지)
    assert any("미판정" in r.message for r in caplog.records)


def test_migration_adds_result_60d(spf_db):
    columns = {row["name"] for row in spf_db.execute("PRAGMA table_info(predictions)").fetchall()}
    assert "result_60d" in columns


def test_judge_60d_hit(spf_db):
    _seed(spf_db, "상승", 100.0)
    assert _judge_col(spf_db, 105.0, "result_60d") == "hit"
