"""학습 차트 보조 지표(이동평균·볼린저·RSI·MACD) 계산과 설정 검증 테스트."""

from __future__ import annotations

import json

import pytest

from dashboard.backend.services import learning_indicators as li
from dashboard.backend.services.learning_settings import (
    DEFAULTS, LearningError, get_settings, update_settings,
)


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


# ---- 계산 ----

def test_sma():
    assert li.sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_ema_first_is_sma_then_alpha():
    out = li.ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == 2
    assert out[3] == pytest.approx(3)  # (4-2)*0.5+2


def test_bollinger_population_std():
    out = li.bollinger([2, 4, 4, 4, 5, 5, 7, 9], 8, 2)
    assert out[:7] == [None] * 7
    assert out[7] == {"upper": 9, "mid": 5, "lower": 1}


def test_rsi_monotonic_and_warmup():
    up = li.rsi([float(i) for i in range(1, 30)], 14)
    assert up[:14] == [None] * 14
    assert all(v == 100 for v in up[14:])
    down = li.rsi([float(i) for i in range(30, 1, -1)], 14)
    assert down[:14] == [None] * 14
    assert all(v == 0 for v in down[14:])


def test_macd_shape():
    vals = [float(i % 7 + i) for i in range(80)]
    out = li.macd(vals, 12, 26, 9)
    assert len(out) == len(vals)
    first = next(i for i, v in enumerate(out) if v is not None)
    assert first == 26 - 1 + 9 - 1
    assert all(v is None for v in out[:first])
    for v in out[first:]:
        assert v["hist"] == pytest.approx(v["macd"] - v["signal"])


def test_short_series_all_none():
    v = [1.0, 2.0, 3.0]
    assert li.sma(v, 5) == [None] * 3
    assert li.ema(v, 5) == [None] * 3
    assert li.bollinger(v, 5, 2) == [None] * 3
    assert li.rsi(v, 5) == [None] * 3
    assert li.macd(v, 12, 26, 9) == [None] * 3


def test_indicator_warmup():
    cfg = json.loads(json.dumps(DEFAULTS["indicators"]))
    assert li.indicator_warmup(cfg) == 52
    cfg["ma"]["enabled"] = True
    assert li.indicator_warmup(cfg) == 120
    cfg["ma"]["enabled"] = False
    cfg["macd"]["enabled"] = True
    assert li.indicator_warmup(cfg) == 105
    cfg["macd"].update(slow=400, signal=100)
    assert li.indicator_warmup(cfg) == 1500


# ---- 설정 ----

def test_defaults(state_db):
    assert get_settings()["indicators"] == {
        "ma": {"enabled": False, "type": "sma", "periods": [5, 20, 60, 120]},
        "bb": {"enabled": False, "period": 20, "stddev": 2.0},
        "volume": {"enabled": False},
        "rsi": {"enabled": False, "period": 14},
        "macd": {"enabled": False, "fast": 12, "slow": 26, "signal": 9},
    }


def test_old_stored_rows_get_indicator_defaults(state_db):
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.execute("INSERT INTO learning_settings(key, value) VALUES (?, ?)",
                     ("wyckoff", json.dumps({"n": 30, "width_pct": 15.0, "vol_mult": 2.0})))
    assert get_settings()["indicators"]["rsi"]["period"] == 14
    out = update_settings({"indicators": {"rsi": {"enabled": True}}})
    assert out["indicators"]["rsi"] == {"enabled": True, "period": 14}


@pytest.mark.parametrize("patch", [
    {"macd": {"fast": 30}},  # fast >= slow
    {"macd": {"fast": 26}},
    {"ma": {"periods": []}},
    {"ma": {"periods": [2, 3, 4, 5, 6, 7, 8]}},
    {"ma": {"periods": [5, 1.5]}},
    {"ma": {"periods": [True]}},
    {"ma": {"periods": [1]}},
    {"ma": {"periods": [401]}},
    {"ma": {"type": "wma"}},
    {"ma": {"enabled": 1}},
    {"bb": {"period": 4}},
    {"bb": {"period": 10.5}},
    {"bb": {"stddev": 5}},
    {"rsi": {"period": 1}},
    {"rsi": {"period": True}},
    {"macd": {"signal": 1}},
    {"macd": {"slow": 401}},
    {"volume": {"enabled": "yes"}},
])
def test_invalid_indicator_settings_rejected(state_db, patch):
    with pytest.raises(LearningError):
        update_settings({"indicators": patch})


def test_valid_update_persists(state_db):
    update_settings({"indicators": {"ma": {"enabled": True, "type": "ema", "periods": [10, 30]}}})
    ma = get_settings()["indicators"]["ma"]
    assert ma == {"enabled": True, "type": "ema", "periods": [10, 30]}
