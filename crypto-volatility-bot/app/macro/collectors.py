"""거시·온체인·BTC일봉 소스 수집 + 일 1회 캐시.

direction_composite.build_factors 가 받을 7개 소스 시계열을 반환한다.
프로덕션(Railway)은 plain HTTPS로 동작. 로컬(Avast HTTPS 스캔 환경)은
환경변수 MACRO_CA_BUNDLE 에 certifi+Avast 루트 결합 번들 경로를 주면 우회
(docs/RESEARCH_direction-signals.md §3 참조).
"""

from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
_CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
_BINANCE_URL = "https://api.binance.com/api/v3/klines"
_HISTORY_DAYS = 420  # 250 워밍업 + 91(13주) + 여유
_SOURCE_COLS = ["close", "eth_close", "sol_close", "net_liquidity", "tga", "dxy", "ust10y", "vix", "mvrv", "active_addr"]


def _verify():
    """로컬 Avast 우회용 CA 번들 경로(있으면) 또는 기본 certifi 검증."""
    return os.getenv("MACRO_CA_BUNDLE") or True


# ── 파싱 (네트워크 무관 — 단위테스트 대상) ──────────────────
def _parse_fred(observations: list[dict]) -> pd.Series:
    rows = [(o["date"], o["value"]) for o in observations if o.get("value") not in (".", None, "")]
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()


def _parse_coinmetrics(data: list[dict], metric: str) -> pd.Series:
    rows = [(o["time"][:10], o.get(metric)) for o in data if o.get(metric) not in (None, "")]
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()


def _parse_binance_klines(klines: list[list]) -> pd.Series:
    if not klines:
        return pd.Series(dtype=float)
    return pd.Series(
        {pd.Timestamp(k[0], unit="ms").normalize(): float(k[4]) for k in klines}
    ).sort_index()


# ── fetch (네트워크) ─────────────────────────────────────────
def _fetch_fred(series_id: str, start: str = "2018-01-01") -> pd.Series:
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY 환경변수 없음")
    r = requests.get(
        _FRED_URL,
        params={"series_id": series_id, "api_key": key, "file_type": "json", "observation_start": start},
        timeout=20, verify=_verify(),
    )
    r.raise_for_status()
    return _parse_fred(r.json()["observations"])


def _fetch_coinmetrics(metric: str, start: str = "2018-01-01") -> pd.Series:
    out: list[dict] = []
    url, params = _CM_URL, {"assets": "btc", "metrics": metric, "frequency": "1d",
                            "start_time": start, "page_size": 10000}
    for _ in range(5):
        r = requests.get(url, params=params, timeout=30, verify=_verify())
        r.raise_for_status()
        j = r.json()
        out.extend(j.get("data", []))
        nxt = j.get("next_page_url")
        if not nxt:
            break
        url, params = nxt, None
    return _parse_coinmetrics(out, metric)


def _fetch_daily(symbol: str = "BTCUSDT", days: int = _HISTORY_DAYS) -> pd.Series:
    """Binance 일봉 종가 시계열 (BTC/ETH/SOL 등)."""
    start = int((time.time() - days * 86400) * 1000)
    now = int(time.time() * 1000)
    rows: list[list] = []
    cur = start
    for _ in range(10):
        r = requests.get(
            _BINANCE_URL,
            params={"symbol": symbol, "interval": "1d", "limit": 1000, "startTime": cur},
            timeout=20, verify=_verify(),
        )
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < 1000 or page[-1][0] >= now:
            break
        cur = page[-1][0] + 86400000
    return _parse_binance_klines(rows)


def fetch_sources() -> dict[str, pd.Series]:
    """소스 시계열을 BTC 일봉 인덱스에 ffill 정렬해 반환.

    매크로(공통) + BTC/ETH/SOL 일봉(자산별 기술지표·도미넌스 프록시용).
    도미넌스는 별도 글로벌 시총 대신 BTC vs 알트 상대강도로 signals에서 계산(자급).
    """
    close = _fetch_daily("BTCUSDT")
    if close.empty:
        raise RuntimeError("BTC 일봉 수집 실패")
    idx = close.index

    def R(s: pd.Series) -> pd.Series:
        return s.reindex(idx, method="ffill")

    walcl, tga, rrp = _fetch_fred("WALCL"), _fetch_fred("WTREGEN"), _fetch_fred("RRPONTSYD")
    tga_d = R(tga)  # TGA 원값(백만$) — 순유동성 성분이자 급변 알림·리더보드 지표 소스
    return {
        "close": close,
        "eth_close": R(_fetch_daily("ETHUSDT")),
        "sol_close": R(_fetch_daily("SOLUSDT")),
        "net_liquidity": R(walcl) - tga_d - R(rrp) * 1000,
        "tga": tga_d,
        "dxy": R(_fetch_fred("DTWEXBGS")),
        "ust10y": R(_fetch_fred("DGS10")),
        "vix": R(_fetch_fred("VIXCLS")),
        "mvrv": R(_fetch_coinmetrics("CapMVRVCur")),
        "active_addr": R(_fetch_coinmetrics("AdrActCnt")),
    }


# ── 캐시 (일 1회) ────────────────────────────────────────────
def _save_sources(sources: dict[str, pd.Series], path: str) -> None:
    pd.DataFrame({k: sources[k] for k in _SOURCE_COLS}).to_csv(path)


def _load_sources(path: str) -> dict[str, pd.Series]:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return {c: df[c] for c in _SOURCE_COLS}


def _is_fresh(path: str, max_age_hours: float) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) / 3600.0 < max_age_hours


def _cache_columns_ok(path: str) -> bool:
    """캐시에 _SOURCE_COLS 전체가 있는지 — 구버전 캐시(예: tga 컬럼 부재) 마이그레이션 감지."""
    try:
        cols = pd.read_csv(path, index_col=0, nrows=0).columns
        return set(_SOURCE_COLS).issubset(cols)
    except Exception:
        return False


def get_sources(cache_path: str, max_age_hours: float = 24.0, fetcher=fetch_sources) -> dict[str, pd.Series]:
    """캐시가 신선하고 컬럼이 완전하면 캐시 사용, 아니면 fetch 후 저장. fetch 실패 시 stale 캐시 폴백."""
    if _is_fresh(cache_path, max_age_hours) and _cache_columns_ok(cache_path):
        return _load_sources(cache_path)
    try:
        sources = fetcher()
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        _save_sources(sources, cache_path)
        return sources
    except Exception as e:
        if os.path.exists(cache_path) and _cache_columns_ok(cache_path):
            logger.warning("거시 소스 fetch 실패 — stale 캐시 사용: %s", e)
            return _load_sources(cache_path)
        raise


def latest_ohlc(symbols: dict[str, str]) -> dict[str, dict]:
    """자산 → 직전 완성 일봉 {close, high, low}. (페이퍼 리밸런스 마크투마켓·청산판정용)

    symbols 예: {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
    klines[-1]은 진행중 봉이므로 완성봉 klines[-2]을 사용.
    """
    out: dict[str, dict] = {}
    for asset, sym in symbols.items():
        r = requests.get(
            _BINANCE_URL,
            params={"symbol": sym, "interval": "1d", "limit": 2},
            timeout=20, verify=_verify(),
        )
        r.raise_for_status()
        k = r.json()
        if not k:
            continue
        bar = k[-2] if len(k) >= 2 else k[-1]
        out[asset] = {"high": float(bar[2]), "low": float(bar[3]), "close": float(bar[4])}
    return out
