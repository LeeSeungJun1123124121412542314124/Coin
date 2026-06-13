"""거시 소스 수집기 — 파싱·캐시 로직 단위 테스트 (네트워크 미사용)."""

from __future__ import annotations

import os

import pandas as pd
import pytest

from app.macro import collectors as C


# ── 파싱 ──────────────────────────────────────────────────────
def test_parse_fred_skips_missing():
    obs = [
        {"date": "2024-01-01", "value": "100.0"},
        {"date": "2024-01-02", "value": "."},      # 결측
        {"date": "2024-01-03", "value": "102.5"},
    ]
    s = C._parse_fred(obs)
    assert len(s) == 2
    assert s.iloc[-1] == 102.5


def test_parse_coinmetrics():
    data = [
        {"time": "2024-01-01T00:00:00.000Z", "CapMVRVCur": "2.5"},
        {"time": "2024-01-02T00:00:00.000Z", "CapMVRVCur": None},
    ]
    s = C._parse_coinmetrics(data, "CapMVRVCur")
    assert len(s) == 1 and s.iloc[0] == 2.5


def test_parse_binance_uses_close():
    kl = [[1704067200000, "1", "2", "0.5", "1.5", "10"]]  # close=인덱스4
    s = C._parse_binance_klines(kl)
    assert s.iloc[0] == 1.5


# ── 캐시 ──────────────────────────────────────────────────────
def _fake_sources():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    return {c: pd.Series(range(10), index=idx, dtype=float) for c in C._SOURCE_COLS}


def test_get_sources_fetches_then_caches(tmp_path):
    path = str(tmp_path / "m.csv")
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return _fake_sources()

    s1 = C.get_sources(path, fetcher=fetch)
    assert calls["n"] == 1 and os.path.exists(path)
    assert set(s1) == set(C._SOURCE_COLS)

    s2 = C.get_sources(path, fetcher=fetch)  # 신선한 캐시 → fetch 안 함
    assert calls["n"] == 1
    assert list(s2["close"]) == list(s1["close"])


def test_get_sources_stale_then_fetch_fail_falls_back(tmp_path):
    path = str(tmp_path / "m.csv")
    C.get_sources(path, fetcher=_fake_sources)  # 캐시 생성

    def boom():
        raise RuntimeError("network down")

    # max_age 0 → stale → fetch 시도 → 실패 → stale 캐시 폴백
    s = C.get_sources(path, max_age_hours=0, fetcher=boom)
    assert set(s) == set(C._SOURCE_COLS)


def test_get_sources_no_cache_and_fetch_fail_raises(tmp_path):
    def boom():
        raise RuntimeError("network down")

    with pytest.raises(RuntimeError):
        C.get_sources(str(tmp_path / "missing.csv"), fetcher=boom)
