"""매크로 데이터 헬스 테스트 — 합성 캐시 CSV, 네트워크 없음."""

from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest

# 복합 산출 점검을 위해 app.macro 임포트 가능하게 (런타임 main.py가 하는 것과 동일)
_BOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "crypto-volatility-bot"))
if _BOT not in sys.path:
    sys.path.insert(0, _BOT)

from dashboard.backend.services.macro_health import macro_health

_COLS = ["close", "eth_close", "sol_close", "net_liquidity", "dxy", "ust10y", "vix", "mvrv", "active_addr"]


def _write_cache(path, n: int) -> date:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    t = np.arange(n)
    df = pd.DataFrame({
        "close": 100 + t + 10 * np.sin(t / 7),
        "eth_close": 50 + 0.5 * t + 8 * np.cos(t / 9),
        "sol_close": 20 + 5 * np.cos(t / 5),
        "net_liquidity": 1e6 + 50 * t + 5e3 * np.sin(t / 15),
        "dxy": 100 + 5 * np.sin(t / 12),
        "ust10y": 3 + 0.5 * np.sin(t / 20),
        "vix": 15 + 5 * np.sin(t / 10),
        "mvrv": 1.5 + 0.5 * np.sin(t / 25),
        "active_addr": 1e5 + 3e3 * np.sin(t / 18),
    }, index=idx)
    df.to_csv(path)
    return idx[-1].date()


def test_no_data():
    h = macro_health(cache_path="/nonexistent/macro_cache.csv")
    assert h["status"] == "no_data" and h["composite"] is None


def test_healthy(tmp_path):
    p = str(tmp_path / "macro_cache.csv")
    last = _write_cache(p, 400)  # 13주차분(91)+min_periods(250)=341 충족
    h = macro_health(cache_path=p, today=last)
    assert h["status"] == "ok"
    assert h["composite"]["ok"] is True and h["composite"]["n_factors"] >= 6
    assert len(h["series"]) == 9


def test_short_cache_composite_not_ok(tmp_path):
    p = str(tmp_path / "macro_cache.csv")
    last = _write_cache(p, 50)  # 워밍업 미달 → 복합 NaN → ok False
    h = macro_health(cache_path=p, today=last)
    assert h["composite"]["ok"] is False
    assert h["status"] == "stale"


def test_stale_by_age(tmp_path):
    p = str(tmp_path / "macro_cache.csv")
    last = _write_cache(p, 400)
    old = __import__("time").time() - 60 * 3600  # 60시간 전
    os.utime(p, (old, old))
    h = macro_health(cache_path=p, today=last)
    assert h["status"] == "stale" and h["cache_age_hours"] > 48
