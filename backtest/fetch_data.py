"""
Bybit 1년치 데이터 수집 스크립트.

수집 대상:
  - BTC/USDT 1h OHLCV (8,760 캔들)
  - BTC/USDT 4h OHLCV (2,190 캔들)
  - OI 1일 히스토리 (365일, 페이징)
  - FR 8h 히스토리 (~1,095건, 페이징)

저장: backtest/data/*.csv
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import ccxt
import httpx
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SYMBOL_CCXT = "BTC/USDT"
SYMBOL_BYBIT = "BTCUSDT"
BASE = "https://api.bybit.com"

# 1년 전 타임스탬프 (ms)
ONE_YEAR_AGO_MS = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp() * 1000)


# ─── OHLCV (ccxt 페이징) ────────────────────────────────────────────────────

def fetch_ohlcv_all(timeframe: str, limit_per_req: int = 1000) -> pd.DataFrame:
    """ccxt로 1년치 OHLCV 수집 (페이징)."""
    exchange = ccxt.bybit({"enableRateLimit": True})
    since = ONE_YEAR_AGO_MS
    all_rows: list[list] = []

    print(f"  [{timeframe}] 수집 시작 (since={datetime.fromtimestamp(since/1000, tz=timezone.utc).date()})...")
    while True:
        try:
            rows = exchange.fetch_ohlcv(SYMBOL_CCXT, timeframe=timeframe, since=since, limit=limit_per_req)
        except Exception as e:
            print(f"  [{timeframe}] 오류: {e}, 재시도 3초 후...")
            time.sleep(3)
            continue

        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        print(f"  [{timeframe}] {len(all_rows)}건 수집 | 마지막: {datetime.fromtimestamp(last_ts/1000, tz=timezone.utc)}")

        # 다음 페이지: 마지막 타임스탬프 + 1틱
        tf_ms = {"1h": 3_600_000, "4h": 14_400_000}[timeframe]
        since = last_ts + tf_ms
        if since > int(datetime.now(timezone.utc).timestamp() * 1000):
            break
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ─── OI 히스토리 (Bybit V5, 페이징) ────────────────────────────────────────

async def fetch_oi_history_full() -> pd.DataFrame:
    """Bybit V5 OI 1일 히스토리, cursor 페이징으로 1년치 수집."""
    all_items: list[dict] = []
    cursor: str | None = None
    cutoff_ms = ONE_YEAR_AGO_MS

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params: dict = {
                "category": "linear",
                "symbol": SYMBOL_BYBIT,
                "intervalTime": "1d",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(f"{BASE}/v5/market/open-interest", params=params)
            resp.raise_for_status()
            result = resp.json().get("result", {})
            items = result.get("list", [])
            next_cursor = result.get("nextPageCursor", "")

            for item in items:
                ts = int(item["timestamp"])
                if ts < cutoff_ms:
                    items = []  # 1년 이전 → 종료
                    break
                all_items.append({"timestamp": ts, "open_interest": float(item["openInterest"])})

            print(f"  [OI] {len(all_items)}건 수집 | cursor={'있음' if next_cursor else '없음'}")

            if not items or not next_cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(0.3)

    df = pd.DataFrame(all_items)
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ─── FR 히스토리 (Bybit V5, cursor 페이징) ──────────────────────────────────

async def fetch_fr_history_full() -> pd.DataFrame:
    """Bybit V5 FR 히스토리, endTime 페이징으로 1년치 수집."""
    all_items: list[dict] = []
    cutoff_ms = ONE_YEAR_AGO_MS
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params: dict = {
                "category": "linear",
                "symbol": SYMBOL_BYBIT,
                "limit": 200,
                "endTime": end_ms,
            }

            resp = await client.get(f"{BASE}/v5/market/funding/history", params=params)
            resp.raise_for_status()
            result = resp.json().get("result", {})
            items = result.get("list", [])

            if not items:
                break

            reached_cutoff = False
            oldest_ts = end_ms
            for item in items:
                ts = int(item["fundingRateTimestamp"])
                if ts < cutoff_ms:
                    reached_cutoff = True
                    break
                all_items.append({"timestamp": ts, "funding_rate": float(item["fundingRate"])})
                oldest_ts = min(oldest_ts, ts)

            print(f"  [FR] {len(all_items)}건 수집 | 가장 오래된: {datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).date()}")

            if reached_cutoff or oldest_ts <= cutoff_ms:
                break
            # 다음 페이지: 현재 배치 가장 오래된 시간 - 1ms
            end_ms = oldest_ts - 1
            await asyncio.sleep(0.3)

    df = pd.DataFrame(all_items)
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ─── 메인 ───────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Bybit BTC/USDT 1년치 데이터 수집")
    print(f"기간: {datetime.fromtimestamp(ONE_YEAR_AGO_MS/1000, tz=timezone.utc).date()} ~ 오늘")
    print("=" * 60)

    # 1. OHLCV 1h
    print("\n[1/4] OHLCV 1h 수집...")
    df_1h = fetch_ohlcv_all("1h")
    path_1h = DATA_DIR / "btc_1h.csv"
    df_1h.to_csv(path_1h, index=False)
    print(f"  → 저장: {path_1h} ({len(df_1h)}행)")

    # 2. OHLCV 4h
    print("\n[2/4] OHLCV 4h 수집...")
    df_4h = fetch_ohlcv_all("4h")
    path_4h = DATA_DIR / "btc_4h.csv"
    df_4h.to_csv(path_4h, index=False)
    print(f"  → 저장: {path_4h} ({len(df_4h)}행)")

    # 3. OI 히스토리
    print("\n[3/4] OI 히스토리 수집...")
    df_oi = await fetch_oi_history_full()
    path_oi = DATA_DIR / "btc_oi_daily.csv"
    df_oi.to_csv(path_oi, index=False)
    print(f"  → 저장: {path_oi} ({len(df_oi)}행)")

    # 4. FR 히스토리
    print("\n[4/4] FR 히스토리 수집...")
    df_fr = await fetch_fr_history_full()
    path_fr = DATA_DIR / "btc_fr_8h.csv"
    df_fr.to_csv(path_fr, index=False)
    print(f"  → 저장: {path_fr} ({len(df_fr)}행)")

    print("\n" + "=" * 60)
    print("수집 완료!")
    print(f"  1h OHLCV  : {len(df_1h):,}건")
    print(f"  4h OHLCV  : {len(df_4h):,}건")
    print(f"  OI (1d)   : {len(df_oi):,}건")
    print(f"  FR (8h)   : {len(df_fr):,}건")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
