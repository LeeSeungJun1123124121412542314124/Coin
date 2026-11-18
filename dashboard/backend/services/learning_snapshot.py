"""체결 시점 온체인·거시 스냅샷 — DB 최신값만 읽는다 (실시간 호출 없음)."""

from __future__ import annotations

from dashboard.backend.db.connection import get_db

# metric -> (scope, source). scope "symbol"은 종목 자체, 나머지는 고정 scope
SNAPSHOT_METRICS: dict[str, tuple[str, str]] = {
    "mvrv": ("BTC", "coinmetrics"),
    "active_addresses": ("BTC", "coinmetrics"),
    "nupl": ("BTC", "coinmetrics"),
    "realized_price": ("BTC", "coinmetrics"),
    "sopr": ("BTC", "bgeometrics"),
    "fee_fastest": ("BTC", "mempool.space"),
    "mempool_tx_count": ("BTC", "mempool.space"),
    "hashrate": ("BTC", "mempool.space"),
    "stablecoin_supply": ("GLOBAL", "defillama"),
    "tga": ("US", "fred"),
    "m2": ("US", "fred"),
    "funding_rate": ("symbol", "binance-futures"),
    "open_interest": ("symbol", "binance-futures"),
    "sol_tvl": ("SOL", "defillama"),
}


def _is_sol(symbol: str) -> bool:
    return symbol.removesuffix("USDT") == "SOL"


def build_snapshot(symbol: str) -> dict:
    items: dict[str, dict] = {}
    with get_db() as conn:
        for metric, (scope_kind, source) in SNAPSHOT_METRICS.items():
            if metric == "sol_tvl" and not _is_sol(symbol):
                continue
            scope = symbol if scope_kind == "symbol" else scope_kind
            row = conn.execute(
                "SELECT value, as_of, source FROM learning_metrics "
                "WHERE metric=? AND scope=? ORDER BY as_of DESC LIMIT 1",
                (metric, scope),
            ).fetchone()
            if row is not None and row[0] is not None:
                items[metric] = {"value": row[0], "as_of": row[1], "source": row[2]}
                continue
            fail = conn.execute(
                "SELECT reason FROM learning_collection_runs "
                "WHERE source=? AND status IN ('failed','rate_limited','skipped') "
                "ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
            items[metric] = {"value": None, "reason": (fail[0] if fail and fail[0] else "수집된 값 없음")}
    return {"symbol": symbol, "items": items}
