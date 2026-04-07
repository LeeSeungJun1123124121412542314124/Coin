"""Backtest TechnicalAnalyzer against real Binance BTC/USDT data.

Fetches 1h candles for a date range, runs TechnicalAnalyzer with sliding window,
and reports detected events (HIGH/MEDIUM signals) with timestamps and price context.
"""

from __future__ import annotations

import sys
import os
import io
import time
from datetime import datetime, timezone

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ccxt
import pandas as pd
import numpy as np

from app.analyzers.technical_analyzer import TechnicalAnalyzer


def fetch_binance_ohlcv(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch historical OHLCV from Binance in chunks."""
    exchange = ccxt.binance({"enableRateLimit": True})

    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    all_data = []
    since = start_ts

    print(f"Fetching {symbol} {timeframe} from {start_date} to {end_date}...")
    while since < end_ts:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"  Error fetching: {e}, retrying...")
            time.sleep(2)
            continue

        if not ohlcv:
            break

        all_data.extend(ohlcv)
        last_ts = ohlcv[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 1
        print(f"  Fetched {len(all_data)} candles so far (up to {datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')})")
        time.sleep(0.5)

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df[df["timestamp"] <= end_ts].reset_index(drop=True)
    print(f"Total: {len(df)} candles\n")
    return df


def run_backtest(
    df: pd.DataFrame,
    df_4h: pd.DataFrame | None = None,
    window_size: int = 100,
    signal_threshold: float = 40.0,
) -> list[dict]:
    """Slide the analyzer over the data and collect significant signals."""
    analyzer = TechnicalAnalyzer()
    n = len(df)
    signals = []

    print(f"Running analysis with window={window_size}, 4h={'yes' if df_4h is not None else 'no'}...")
    for end in range(window_size, n):
        window_df = df.iloc[end - window_size : end][["open", "high", "low", "close", "volume"]].reset_index(drop=True)

        # 4h 데이터: 현재 1h 봉의 타임스탬프까지의 4h 슬라이스 (최근 50봉)
        window_4h = None
        if df_4h is not None:
            current_ts = df.iloc[end - 1]["timestamp"]
            mask = df_4h["timestamp"] <= current_ts
            slice_4h = df_4h[mask].tail(50)[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
            if len(slice_4h) >= 20:
                window_4h = slice_4h

        try:
            result = analyzer.analyze(window_df, df_4h=window_4h)
        except Exception:
            continue

        row = df.iloc[end - 1]
        sig = {
            "bar_index": end,
            "datetime": row["datetime"],
            "close": float(row["close"]),
            "score": result.score,
            "signal": result.signal,
            "base_score": result.details.get("base_score", 0.0),
            "boosters": result.details.get("signal_boost", {}).get("active_boosters", {}),
            "boost_total": result.details.get("signal_boost", {}).get("total_boost", 0.0),
        }
        signals.append(sig)

        if end % 500 == 0:
            print(f"  Processed {end}/{n} bars...")

    print(f"  Done: {len(signals)} analysis points\n")
    return signals


def find_price_events(df: pd.DataFrame, pct_threshold: float = 5.0, window_hours: int = 24) -> list[dict]:
    """Find significant price moves (>pct_threshold% in window_hours)."""
    events = []
    n = len(df)
    window = window_hours  # 1h candles

    for i in range(window, n):
        close_now = float(df.iloc[i]["close"])
        close_past = float(df.iloc[i - window]["close"])
        pct_change = (close_now - close_past) / close_past * 100.0

        if abs(pct_change) >= pct_threshold:
            events.append({
                "index": i,
                "datetime": df.iloc[i]["datetime"],
                "close": close_now,
                "close_before": close_past,
                "pct_change": pct_change,
                "type": "CRASH" if pct_change < 0 else "RALLY",
            })

    # Deduplicate: keep only the peak of each event (local max of abs(pct_change))
    if not events:
        return []

    deduped = [events[0]]
    for evt in events[1:]:
        prev = deduped[-1]
        hours_apart = (evt["datetime"] - prev["datetime"]).total_seconds() / 3600
        if hours_apart < 48 and evt["type"] == prev["type"]:
            # Same event cluster: keep the more extreme one
            if abs(evt["pct_change"]) > abs(prev["pct_change"]):
                deduped[-1] = evt
        else:
            deduped.append(evt)

    return deduped


def print_report(signals: list[dict], events: list[dict], df: pd.DataFrame):
    """Print analysis results."""
    print("=" * 80)
    print("  BACKTEST REPORT: BTC/USDT 1h")
    print(f"  Period: {df.iloc[0]['datetime'].strftime('%Y-%m-%d')} ~ {df.iloc[-1]['datetime'].strftime('%Y-%m-%d')}")
    print(f"  Total candles: {len(df)}")
    print("=" * 80)

    # 1. Score distribution
    scores = [s["score"] for s in signals]
    high_count = sum(1 for s in signals if s["signal"] == "HIGH")
    medium_count = sum(1 for s in signals if s["signal"] == "MEDIUM")
    low_count = sum(1 for s in signals if s["signal"] == "LOW")

    print(f"\n--- Score Distribution ---")
    print(f"  HIGH signals:   {high_count}")
    print(f"  MEDIUM signals: {medium_count}")
    print(f"  LOW signals:    {low_count}")
    print(f"  Avg score:      {np.mean(scores):.1f}")
    print(f"  Max score:      {np.max(scores):.1f}")
    print(f"  Min score:      {np.min(scores):.1f}")

    # 2. Significant price events
    print(f"\n--- Major Price Events (>5% in 24h) ---")
    if not events:
        print("  None found in this period.")
    for evt in events:
        emoji = "📉" if evt["type"] == "CRASH" else "📈"
        print(f"  {emoji} {evt['datetime'].strftime('%Y-%m-%d %H:%M')} | "
              f"{evt['type']:5s} | {evt['pct_change']:+.1f}% | "
              f"${evt['close_before']:,.0f} -> ${evt['close']:,.0f}")

    # 3. HIGH/MEDIUM signals timeline
    significant = [s for s in signals if s["signal"] in ("HIGH", "MEDIUM")]
    # Deduplicate: group signals within 12h windows
    deduped_sigs = []
    for sig in significant:
        if not deduped_sigs:
            deduped_sigs.append(sig)
            continue
        hours_apart = (sig["datetime"] - deduped_sigs[-1]["datetime"]).total_seconds() / 3600
        if hours_apart < 12:
            if sig["score"] > deduped_sigs[-1]["score"]:
                deduped_sigs[-1] = sig
        else:
            deduped_sigs.append(sig)

    print(f"\n--- Signal Timeline (HIGH/MEDIUM, deduped 12h window) ---")
    if not deduped_sigs:
        print("  No HIGH/MEDIUM signals detected.")
    for sig in deduped_sigs:
        boosters_str = ", ".join(f"{k}(+{v:.0f})" for k, v in sig["boosters"].items()) if sig["boosters"] else "none"
        base = sig.get("base_score", 0.0)
        print(f"  {'🔴' if sig['signal'] == 'HIGH' else '🟡'} {sig['datetime'].strftime('%Y-%m-%d %H:%M')} | "
              f"{sig['signal']:6s} | score={sig['score']:.1f} base={base:.1f} | "
              f"${sig['close']:,.0f} | boost={sig['boost_total']:.0f} [{boosters_str}]")

    # 4. Event detection accuracy
    print(f"\n--- Event Detection Analysis ---")
    for evt in events:
        evt_time = evt["datetime"]
        # Check if any HIGH/MEDIUM signal was within 24h before the event peak
        detected = False
        best_signal = None
        for sig in deduped_sigs:
            hours_before = (evt_time - sig["datetime"]).total_seconds() / 3600
            if -6 <= hours_before <= 24:  # signal within 24h before or 6h after
                if best_signal is None or sig["score"] > best_signal["score"]:
                    best_signal = sig
                    detected = True

        emoji = "📉" if evt["type"] == "CRASH" else "📈"
        status = "DETECTED" if detected else "MISSED"
        status_icon = "✅" if detected else "❌"
        detail = ""
        if best_signal:
            hours_diff = (evt_time - best_signal["datetime"]).total_seconds() / 3600
            detail = f" | signal {hours_diff:+.0f}h, score={best_signal['score']:.1f}"
        print(f"  {status_icon} {emoji} {evt['datetime'].strftime('%Y-%m-%d %H:%M')} "
              f"{evt['type']:5s} {evt['pct_change']:+.1f}% -> {status}{detail}")

    detected_count = sum(1 for evt in events if any(
        -6 <= (evt["datetime"] - sig["datetime"]).total_seconds() / 3600 <= 24
        for sig in deduped_sigs
    ))
    total_events = len(events)
    if total_events > 0:
        print(f"\n  Detection rate: {detected_count}/{total_events} ({detected_count/total_events*100:.0f}%)")

    # 5. False positive analysis
    print(f"\n--- False Positive Analysis ---")
    false_positives = []
    for sig in deduped_sigs:
        # Check if there's a >3% move within 24h after the signal
        sig_idx = sig["bar_index"]
        if sig_idx + 24 < len(df):
            future_high = df.iloc[sig_idx:sig_idx+24]["high"].max()
            future_low = df.iloc[sig_idx:sig_idx+24]["low"].min()
            close_at_signal = sig["close"]
            max_up = (future_high - close_at_signal) / close_at_signal * 100
            max_down = (future_low - close_at_signal) / close_at_signal * 100
            max_move = max(abs(max_up), abs(max_down))
            if max_move < 3.0:
                false_positives.append(sig)

    print(f"  Total HIGH/MEDIUM signals: {len(deduped_sigs)}")
    print(f"  Followed by >3% move (24h): {len(deduped_sigs) - len(false_positives)}")
    print(f"  No significant move (FP):   {len(false_positives)}")
    if deduped_sigs:
        fp_rate = len(false_positives) / len(deduped_sigs) * 100
        print(f"  False positive rate:        {fp_rate:.0f}%")

    # 6. Boost-segmented FP analysis
    print(f"\n--- Boost-Segmented Analysis ---")
    boosted_sigs = [s for s in deduped_sigs if s["boost_total"] > 0]
    base_only_sigs = [s for s in deduped_sigs if s["boost_total"] == 0]

    boosted_fp = [s for s in false_positives if s["boost_total"] > 0]
    base_only_fp = [s for s in false_positives if s["boost_total"] == 0]

    print(f"  Boosted signals (boost>0):  {len(boosted_sigs)} total, {len(boosted_fp)} FP", end="")
    if boosted_sigs:
        print(f" ({len(boosted_fp)/len(boosted_sigs)*100:.0f}%)")
    else:
        print()
    print(f"  Base-only signals (boost=0): {len(base_only_sigs)} total, {len(base_only_fp)} FP", end="")
    if base_only_sigs:
        print(f" ({len(base_only_fp)/len(base_only_sigs)*100:.0f}%)")
    else:
        print()

    print(f"\n{'=' * 80}")


def main():
    start_date = "2025-08-14"
    end_date = "2026-02-19"

    # 1h 데이터 fetch
    df = fetch_binance_ohlcv(symbol="BTC/USDT", timeframe="1h", start_date=start_date, end_date=end_date)
    if len(df) < 200:
        print("ERROR: Not enough data fetched.")
        sys.exit(1)

    # 4h 데이터 fetch (타임스탬프 컬럼 유지)
    df_4h = fetch_binance_ohlcv(symbol="BTC/USDT", timeframe="4h", start_date=start_date, end_date=end_date)

    # Run analysis
    signals = run_backtest(df, df_4h=df_4h, window_size=100, signal_threshold=40.0)

    # Find significant price events
    events = find_price_events(df, pct_threshold=5.0, window_hours=24)

    # Print report
    print_report(signals, events, df)


if __name__ == "__main__":
    main()
