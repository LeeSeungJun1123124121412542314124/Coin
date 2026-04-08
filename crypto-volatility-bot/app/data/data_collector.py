"""DataCollector — fetches OHLCV, Fear & Greed, Coin Metrics onchain, and Bybit OI/FR."""

from __future__ import annotations

import logging
import time
from typing import Any

import ccxt
import pandas as pd
import requests

_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
_COINMETRICS_BASE = "https://community-api.coinmetrics.io/v4"
_BYBIT_BASE = "https://api.bybit.com"
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0

# Coin Metrics asset name mapping (BTC/USDT → btc)
_ASSET_MAP = {"btc": "btc", "eth": "eth", "xrp": "xrp"}

logger = logging.getLogger(__name__)


def _retry(fn, *args, retries: int = _MAX_RETRIES, **kwargs) -> Any:
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning(
                "시도 %d/%d 실패 (%s): %s",
                attempt + 1,
                retries,
                type(e).__name__,
                e,
            )
            if attempt == retries - 1:
                logger.error("최대 재시도 횟수(%d) 초과: %s", retries, e)
                return None
            time.sleep(_BACKOFF_BASE * (2**attempt))
    return None


class DataCollector:
    def __init__(
        self,
        bybit_api_key: str | None = None,
        bybit_api_secret: str | None = None,
    ) -> None:
        self._binance_key = bybit_api_key
        self._binance_secret = bybit_api_secret
        self._exchange: ccxt.Exchange | None = None  # 인스턴스 재사용

    def _make_exchange(self) -> ccxt.Exchange:
        params: dict[str, Any] = {"enableRateLimit": True}
        if self._binance_key:
            params["apiKey"] = self._binance_key
            params["secret"] = self._binance_secret
        return ccxt.bybit(params)

    def _get_exchange(self) -> ccxt.Exchange:
        """ccxt Exchange 인스턴스 재사용 (최초 1회만 생성)."""
        if self._exchange is None:
            self._exchange = self._make_exchange()
        return self._exchange

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
        def _fetch():
            exchange = self._get_exchange()  # 재사용
            raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df = df.drop(columns=["timestamp"])
            return df

        return _retry(_fetch)

    def fetch_fear_greed(self) -> int | None:
        def _fetch():
            resp = requests.get(_FEAR_GREED_URL, timeout=10)
            resp.raise_for_status()
            return int(resp.json()["data"][0]["value"])

        return _retry(_fetch)

    def fetch_onchain_data(self, coin: str = "btc") -> dict[str, Any] | None:
        """Fetch exchange inflow/outflow from Coin Metrics Community API (no API key needed)."""
        asset = _ASSET_MAP.get(coin.lower(), coin.lower())

        def _fetch():
            resp = requests.get(
                f"{_COINMETRICS_BASE}/timeseries/asset-metrics",
                params={
                    "assets": asset,
                    "metrics": "FlowInExNtv,FlowOutExNtv,AdrActCnt",
                    "frequency": "1d",
                    "limit_per_asset": 1,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                return None
            latest = data[0]
            inflow = float(latest.get("FlowInExNtv") or 0)
            outflow = float(latest.get("FlowOutExNtv") or 0)
            active_addresses = float(latest.get("AdrActCnt") or 0)
            # Whale proxy: active addresses 비율로 추정 (고래 활동 대리지표)
            whale_proxy = inflow + outflow  # 총 유동량이 클수록 고래 활동 가능성
            return {
                "exchange_inflow": inflow,
                "exchange_outflow": outflow,
                "whale_transaction_volume": whale_proxy / 1000,  # 정규화
                "dormant_whale_activated": False,
            }

        return _retry(_fetch)

    def fetch_derivatives(self, symbol: str = "BTC/USDT") -> dict[str, Any] | None:
        """Bybit V5에서 OI(미결제약정) 현재값 + 3일 전 값, FR(펀딩레이트) 수집.

        Returns:
            {"oi_current": float, "oi_3d_ago": float, "funding_rate": float}
            실패 시 None (파이프라인에서 NEUTRAL 폴백 처리)
        """
        bybit_symbol = symbol.replace("/", "").replace("-", "")  # BTC/USDT → BTCUSDT

        def _fetch():
            # OI 히스토리 (최근 4일치, 1d 간격)
            oi_resp = requests.get(
                f"{_BYBIT_BASE}/v5/market/open-interest",
                params={
                    "category": "linear",
                    "symbol": bybit_symbol,
                    "intervalTime": "1d",
                    "limit": 4,
                },
                timeout=10,
            )
            oi_resp.raise_for_status()
            oi_items = oi_resp.json().get("result", {}).get("list", [])
            if len(oi_items) < 2:
                return None

            # Bybit 응답은 최신순 → items[0] = 최신, items[-1] = 가장 오래된
            oi_current = float(oi_items[0]["openInterest"])
            oi_3d_ago = float(oi_items[-1]["openInterest"])

            # FR 최근값
            fr_resp = requests.get(
                f"{_BYBIT_BASE}/v5/market/funding/history",
                params={
                    "category": "linear",
                    "symbol": bybit_symbol,
                    "limit": 1,
                },
                timeout=10,
            )
            fr_resp.raise_for_status()
            fr_items = fr_resp.json().get("result", {}).get("list", [])
            funding_rate = float(fr_items[0]["fundingRate"]) if fr_items else 0.0

            return {
                "oi_current": oi_current,
                "oi_3d_ago": oi_3d_ago,
                "funding_rate": funding_rate,
            }

        return _retry(_fetch)
