"""지수 방향 판정 그림자 기록 job."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from dashboard.backend.collectors.yahoo_finance import fetch_index_history
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)

_INDEX_SYMBOLS = ("^KS11", "^GSPC")
_HORIZONS = {
    7: ("price_after_7d", "result_7d"),
    14: ("price_after_14d", "result_14d"),
    30: ("price_after_30d", "result_30d"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


def get_sources(cache_path: str) -> dict[str, pd.Series]:
    from app.macro.collectors import get_sources as _get_sources

    return _get_sources(cache_path)


def direction_from_z(z: float | None) -> str:
    if z is None or z != z:
        return "neutral"
    if z >= 0.5:
        return "long"
    if z <= -0.5:
        return "short"
    return "neutral"


def _history_to_close_series(history: list[dict]) -> pd.Series:
    rows = {
        pd.Timestamp(row["date"]): float(row["close"])
        for row in history
        if row.get("date") and row.get("close") is not None
    }
    return pd.Series(rows).sort_index()


def _latest_value(series: pd.Series) -> float | None:
    values = series.dropna()
    if values.empty:
        return None
    return round(float(values.iloc[-1]), 3)


def _align_sources_to_close(sources: dict[str, pd.Series], close: pd.Series) -> dict[str, pd.Series]:
    aligned: dict[str, pd.Series] = {"close": close}
    for key, value in sources.items():
        if key == "close" or not isinstance(value, pd.Series):
            continue
        aligned[key] = value.reindex(close.index, method="ffill")
    return aligned


def build_index_shadow_records(
    symbol: str,
    history: list[dict],
    sources: dict[str, pd.Series],
    created_at: str,
) -> list[dict]:
    from app.macro.signals import INDICATORS, _bollinger_sig, _rsi_sig, build_context

    close = _history_to_close_series(history)
    if close.empty:
        return []
    ctx = build_context(_align_sources_to_close(sources, close))
    indicator_fns = {
        "RSI": lambda: _rsi_sig(ctx, "BTC"),
        "볼린저밴드": lambda: _bollinger_sig(ctx, "BTC"),
        "과열회귀": lambda: INDICATORS["과열회귀"](ctx, "BTC"),
        "VIX": lambda: INDICATORS["VIX"](ctx, "BTC"),
        "순유동성": lambda: INDICATORS["순유동성"](ctx, "BTC"),
        "긴축환경": lambda: INDICATORS["긴축환경"](ctx, "BTC"),
        "유동성": lambda: INDICATORS["유동성"](ctx, "BTC"),
    }

    latest_date = close.index[-1].date().isoformat()
    latest_price = round(float(close.iloc[-1]), 4)
    records: list[dict] = []
    z_values: list[float] = []
    for indicator, fn in indicator_fns.items():
        z = _latest_value(fn())
        if z is not None:
            z_values.append(z)
        records.append({
            "date": latest_date,
            "symbol": symbol,
            "indicator": indicator,
            "z": z,
            "direction": direction_from_z(z),
            "price": latest_price,
            "created_at": created_at,
        })

    composite_z = round(sum(z_values) / len(z_values), 3) if z_values else None
    records.append({
        "date": latest_date,
        "symbol": symbol,
        "indicator": "복합",
        "z": composite_z,
        "direction": direction_from_z(composite_z),
        "price": latest_price,
        "created_at": created_at,
    })
    return records


def upsert_index_shadow_records(records: list[dict]) -> int:
    if not records:
        return 0
    with get_db() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO index_shadow_judgments
               (date, symbol, indicator, z, direction, price, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    record["date"],
                    record["symbol"],
                    record["indicator"],
                    record["z"],
                    record["direction"],
                    record["price"],
                    record["created_at"],
                )
                for record in records
            ],
        )
    return len(records)


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def judge_index_shadow() -> None:
    cache_path = os.getenv("MACRO_CACHE_PATH", "macro_cache.csv")
    sources = get_sources(cache_path)
    created_at = _utc_now().isoformat()
    total = 0
    for symbol in _INDEX_SYMBOLS:
        history = await fetch_index_history(symbol, days=365, range="1y")
        if not history:
            logger.warning("지수 그림자 판정 스킵: %s 히스토리 없음", symbol)
            continue
        total += upsert_index_shadow_records(
            build_index_shadow_records(symbol, history, sources, created_at)
        )
    logger.info("지수 그림자 판정 저장: %d행", total)


def _nearest_price_on_or_after(history: list[dict], target: date) -> float | None:
    for row in history:
        row_date = date.fromisoformat(row["date"])
        if row_date >= target and row.get("close") is not None:
            return float(row["close"])
    return None


def _judge_result(direction: str, price_then: float, price_after: float) -> str:
    if direction == "neutral":
        return "neutral"
    change_pct = (price_after - price_then) / price_then * 100
    if direction == "long" and change_pct > 1.0:
        return "hit"
    if direction == "short" and change_pct < -1.0:
        return "hit"
    return "miss"


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def settle_index_shadow() -> None:
    today = _today()
    for symbol in _INDEX_SYMBOLS:
        history = await fetch_index_history(symbol, days=365, range="1y")
        if not history:
            logger.warning("지수 그림자 정산 스킵: %s 히스토리 없음", symbol)
            continue
        with get_db() as conn:
            for days, (price_col, result_col) in _HORIZONS.items():
                due_date = (today - timedelta(days=days)).isoformat()
                rows = conn.execute(
                    f"""SELECT date, indicator, direction, price
                        FROM index_shadow_judgments
                        WHERE symbol = ?
                          AND date <= ?
                          AND {result_col} IS NULL""",
                    (symbol, due_date),
                ).fetchall()
                for row in rows:
                    price_after = _nearest_price_on_or_after(
                        history,
                        date.fromisoformat(row["date"]) + timedelta(days=days),
                    )
                    if price_after is None:
                        continue
                    result = _judge_result(row["direction"], row["price"], price_after)
                    conn.execute(
                        f"""UPDATE index_shadow_judgments
                            SET {price_col} = ?, {result_col} = ?
                            WHERE date = ? AND symbol = ? AND indicator = ?""",
                        (price_after, result, row["date"], symbol, row["indicator"]),
                    )
