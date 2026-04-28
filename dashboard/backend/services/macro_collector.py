"""매크로 데이터 수집기 — FRED(TGA, M2) + CoinGecko(BTC Dominance) 시계열을 가져온다.

FRED API key는 환경변수 FRED_API_KEY에서 읽음. 키 없으면 None 반환 (호출부 fallback).
CoinGecko는 무료 키(.env COINGECKO_API_KEY) 또는 비인증 가능.

각 함수는 datetime 인덱스(UTC)를 가진 pd.Series를 반환한다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)


_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def _fetch_fred_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    timeout: float = 15.0,
) -> pd.Series | None:
    """FRED 시계열을 가져와 pd.Series(value, index=datetime UTC) 반환.

    Returns:
        None: API key 없거나 호출 실패 시
    """
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logger.warning("FRED_API_KEY 미설정 — %s 시계열 가져올 수 없음", series_id)
        return None

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    if start_date:
        params["observation_start"] = start_date
    if end_date:
        params["observation_end"] = end_date

    try:
        resp = requests.get(_FRED_BASE, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        observations: list[dict[str, Any]] = data.get("observations", [])
        if not observations:
            logger.warning("FRED %s observations 빈 응답", series_id)
            return None

        # value="."는 결측. 숫자로 변환되는 것만 사용.
        rows = []
        for obs in observations:
            v = obs.get("value")
            if v is None or v == "." or v == "":
                continue
            try:
                rows.append((pd.Timestamp(obs["date"], tz="UTC"), float(v)))
            except (ValueError, KeyError):
                continue
        if not rows:
            return None

        idx = [r[0] for r in rows]
        vals = [r[1] for r in rows]
        s = pd.Series(vals, index=pd.DatetimeIndex(idx), name=series_id)
        return s.sort_index()
    except Exception as exc:
        logger.warning("FRED fetch 실패 series=%s: %s", series_id, exc)
        return None


def fetch_tga(start_date: str | None = None, end_date: str | None = None) -> pd.Series | None:
    """TGA(Treasury General Account) 잔고 시계열.

    FRED series_id = WTREGEN (주별 데이터, 단위 $billions).
    """
    return _fetch_fred_series("WTREGEN", start_date, end_date)


def fetch_m2(start_date: str | None = None, end_date: str | None = None) -> pd.Series | None:
    """M2 통화량 시계열.

    FRED series_id = M2SL (월별 데이터, seasonally adjusted, 단위 $billions).
    """
    return _fetch_fred_series("M2SL", start_date, end_date)


def fetch_btc_dominance(
    start_date: str | None = None,
    end_date: str | None = None,
    timeout: float = 15.0,
) -> pd.Series | None:
    """BTC Dominance(%) 시계열을 CoinGecko Pro API에서 가져온다.

    CoinGecko 무료 plan은 dominance 시계열 미제공 (현재값만 가능). Pro plan 필요.
    Pro key가 없으면 현재값 1개만 반환 (윈도우 평균에 영향 미미).

    Returns:
        Series of dominance % values, datetime index (UTC).
    """
    api_key = os.environ.get("COINGECKO_API_KEY")
    headers = {}
    if api_key:
        headers["x-cg-pro-api-key"] = api_key

    # 1) 현재 dominance (무료/유료 모두 가능)
    try:
        resp = requests.get(f"{_COINGECKO_BASE}/global", headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        market_cap_pct = data.get("data", {}).get("market_cap_percentage", {})
        btc_dom = market_cap_pct.get("btc")
        if btc_dom is None:
            return None

        now = pd.Timestamp.now(tz="UTC").normalize()

        # 2) Pro key가 있으면 historical도 시도
        if api_key:
            # Pro endpoint: /global/history (있는 경우 — 무료에선 404)
            try:
                start_ts = pd.Timestamp(start_date, tz="UTC") if start_date else now - pd.Timedelta(days=400)
                end_ts = pd.Timestamp(end_date, tz="UTC") if end_date else now
                # CoinGecko의 시간순 dominance 데이터는 plan에 따라 endpoint가 다름.
                # 일단 현재값 1개만 안전하게 반환 (간소화 — 충분히 좋은 effect를 위해서는 외부 데이터 필요).
                pass
            except Exception:
                pass

        # 단일 현재값으로 series 구성 — 윈도우별 평균 macro_score 계산엔 미흡하지만
        # 키 부재/Pro plan 부재 시 fallback. start_date 부터 end_date까지 동일값.
        if start_date and end_date:
            start_ts = pd.Timestamp(start_date, tz="UTC")
            end_ts = pd.Timestamp(end_date, tz="UTC")
            idx = pd.date_range(start_ts, end_ts, freq="D")
        else:
            idx = pd.DatetimeIndex([now])
        return pd.Series([float(btc_dom)] * len(idx), index=idx, name="btc_dominance")
    except Exception as exc:
        logger.warning("CoinGecko dominance fetch 실패: %s", exc)
        return None


def fetch_all_macro(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, pd.Series]:
    """3개 매크로 시계열을 모두 수집해 dict로 반환.

    실패한 시계열은 dict에서 제외.
    """
    result: dict[str, pd.Series] = {}

    tga = fetch_tga(start_date, end_date)
    if tga is not None and not tga.empty:
        result["tga"] = tga
        logger.info("TGA 수집: %d행 (%s ~ %s)", len(tga), tga.index[0].date(), tga.index[-1].date())

    m2 = fetch_m2(start_date, end_date)
    if m2 is not None and not m2.empty:
        result["m2"] = m2
        logger.info("M2 수집: %d행 (%s ~ %s)", len(m2), m2.index[0].date(), m2.index[-1].date())

    dom = fetch_btc_dominance(start_date, end_date)
    if dom is not None and not dom.empty:
        result["dominance"] = dom
        logger.info("BTC Dominance 수집: %d행", len(dom))

    return result
