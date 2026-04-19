"""대시보드 코인 슬롯 리포지토리."""

from __future__ import annotations

from dashboard.backend.db.connection import get_db


def get_slots() -> list[dict]:
    """모든 슬롯 조회.

    Returns:
        각 슬롯을 dict로 변환한 리스트. position 순서대로 정렬.
    """
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT position, coin_id, symbol, tv_symbol, updated_at "
            "FROM dashboard_coin_slots "
            "ORDER BY position"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_slot(
    position: int,
    coin_id: str,
    symbol: str,
    tv_symbol: str | None = None
) -> None:
    """슬롯 업데이트.

    Args:
        position: 슬롯 위치 (0-6)
        coin_id: 코인 ID (CoinGecko)
        symbol: 심볼 (예: BTC, ETH)
        tv_symbol: TradingView 심볼 (예: BINANCE:BTCUSDT)
    """
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE dashboard_coin_slots "
            "SET coin_id = ?, symbol = ?, tv_symbol = ?, updated_at = datetime('now') "
            "WHERE position = ?",
            (coin_id, symbol, tv_symbol, position)
        )
        if cursor.rowcount == 0:
            raise ValueError(f"유효하지 않은 슬롯 위치: {position}")
