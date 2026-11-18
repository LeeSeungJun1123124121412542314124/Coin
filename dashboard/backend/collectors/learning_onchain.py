"""학습 탭 온체인·거시 지표 수집기 (무료·키 불필요 API만 사용).

각 fetch 함수는 {"metric","scope","as_of","value","source"} 행 리스트를 반환하고,
실패는 예외로 전달한다 (기록·알림은 jobs/learning_collect.py 담당).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from dashboard.backend.collectors import fred

_TIMEOUT = 10


class SourceError(Exception):
    """사유 문자열이 곧 메시지인 수집 실패 (URL·키 미포함)."""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ts_date(ts: int | float | str) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _row(metric: str, scope: str, as_of: str, value: float, source: str) -> dict:
    return {"metric": metric, "scope": scope, "as_of": as_of, "value": float(value), "source": source}


def derive_nupl_realized(mvrv: float, price: float) -> tuple[float, float]:
    """MVRV와 가격으로 NUPL(1 - 1/MVRV)과 실현가격(가격 / MVRV)을 유도."""
    return 1 - 1 / mvrv, price / mvrv


async def _get_json(url: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def fetch_coinmetrics_btc() -> list[dict]:
    """CoinMetrics Community: MVRV·활성주소·가격 → mvrv/active_addresses/nupl/realized_price."""
    start = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%d")
    data = await _get_json(
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
        {"assets": "btc", "metrics": "CapMVRVCur,AdrActCnt,PriceUSD", "frequency": "1d",
         "start_time": start, "page_size": 10},
    )
    rows: list[dict] = []
    for item in data.get("data", []):
        try:
            mvrv = float(item["CapMVRVCur"])
            addr = float(item["AdrActCnt"])
            price = float(item["PriceUSD"])
        except (KeyError, TypeError, ValueError):
            continue  # 값이 비어 있는 날은 건너뜀
        as_of = item["time"][:10]
        nupl, realized = derive_nupl_realized(mvrv, price)
        rows += [
            _row("mvrv", "BTC", as_of, mvrv, "coinmetrics"),
            _row("active_addresses", "BTC", as_of, addr, "coinmetrics"),
            _row("nupl", "BTC", as_of, nupl, "coinmetrics"),
            _row("realized_price", "BTC", as_of, realized, "coinmetrics"),
        ]
    if not rows:
        raise SourceError("CoinMetrics 응답에 유효한 값 없음")
    return rows


async def fetch_mempool() -> list[dict]:
    """mempool.space: 수수료·멤풀 건수·해시레이트."""
    base = "https://mempool.space"
    fees = await _get_json(f"{base}/api/v1/fees/recommended")
    pool = await _get_json(f"{base}/api/mempool")
    hash_data = await _get_json(f"{base}/api/v1/mining/hashrate/3d")
    today = _today()
    last = hash_data["hashrates"][-1]
    return [
        _row("fee_fastest", "BTC", today, fees["fastestFee"], "mempool.space"),
        _row("mempool_tx_count", "BTC", today, pool["count"], "mempool.space"),
        _row("hashrate", "BTC", _ts_date(last["timestamp"]), last["avgHashrate"], "mempool.space"),
    ]


async def fetch_defillama() -> list[dict]:
    """DefiLlama: 스테이블코인 총 공급량(GLOBAL), 솔라나 TVL(SOL)."""
    stable = await _get_json("https://stablecoins.llama.fi/stablecoincharts/all")
    tvl = await _get_json("https://api.llama.fi/v2/historicalChainTvl/Solana")
    last_s = stable[-1]
    last_t = tvl[-1]
    return [
        _row("stablecoin_supply", "GLOBAL", _ts_date(last_s["date"]),
             last_s["totalCirculatingUSD"]["peggedUSD"], "defillama"),
        _row("sol_tvl", "SOL", _ts_date(last_t["date"]), last_t["tvl"], "defillama"),
    ]


async def fetch_binance_futures(symbol: str) -> list[dict]:
    """바이낸스 선물 펀딩비·미결제약정. 선물이 없는 종목(HTTP 400)은 빈 리스트."""
    base = "https://fapi.binance.com"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        prem = await client.get(f"{base}/fapi/v1/premiumIndex", params={"symbol": symbol})
        if prem.status_code == 400:
            return []
        prem.raise_for_status()
        oi = await client.get(f"{base}/fapi/v1/openInterest", params={"symbol": symbol})
        if oi.status_code == 400:
            return []
        oi.raise_for_status()
    today = _today()
    return [
        _row("funding_rate", symbol, today, prem.json()["lastFundingRate"], "binance-futures"),
        _row("open_interest", symbol, today, oi.json()["openInterest"], "binance-futures"),
    ]


async def fetch_bgeometrics_sopr() -> list[dict]:
    """BGeometrics 무료 엔드포인트(키 불필요, 지연 데이터)의 최신 SOPR."""
    data = await _get_json("https://bitcoin-data.com/v1/sopr/last")
    return [_row("sopr", "BTC", data["d"], data["sopr"], "bgeometrics")]


async def fetch_fred_liquidity() -> list[dict]:
    """FRED TGA·M2 (기존 collectors/fred 재사용). 값이 비면 실패."""
    rows: list[dict] = []
    for metric, fn in (("tga", fred.fetch_tga), ("m2", fred.fetch_m2)):
        series = await fn()
        if not series:
            raise SourceError("FRED 값 없음(키 미설정 또는 조회 실패)")
        rows += [_row(metric, "US", p["date"], p["value"], "fred") for p in series]
    return rows
