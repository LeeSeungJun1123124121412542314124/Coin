"""페이퍼 트레이딩 리더보드 — 일일 리밸런스 잡.

app.macro 신호 + 최신 일봉 시세 → 지표별 포트폴리오 리밸런스 + 에쿼티 스냅샷.
(런타임 main.py가 crypto-volatility-bot을 sys.path에 추가하므로 app.macro 임포트 가능)
스펙: docs/SPEC_paper-trading-leaderboard.md (#3 일 1회 UTC 00:05)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


def run_paper_rebalance() -> None:
    """모든 지표 포트폴리오를 최신 신호·시세로 1일 리밸런스."""
    from app.macro.collectors import get_sources, latest_ohlc
    from app.macro.signals import INDICATORS, latest_signals
    from dashboard.backend.services.paper_engine import ensure_portfolios, rebalance

    cache_path = os.getenv("MACRO_CACHE_PATH", "macro_cache.csv")
    sources = get_sources(cache_path)
    signals = latest_signals(sources)
    prices = latest_ohlc(_SYMBOLS)
    if not prices:
        logger.warning("paper_rebalance: 시세 조회 실패 — 스킵")
        return

    ensure_portfolios(list(INDICATORS))
    at = datetime.now(timezone.utc).isoformat()
    ok = 0
    for ind in INDICATORS:
        try:
            rebalance(ind, signals.get(ind, {}), prices, at)
            ok += 1
        except Exception as e:
            logger.error("paper_rebalance(%s) 실패: %s", ind, e, exc_info=True)
    logger.info("paper_rebalance 완료: %d/%d개 지표", ok, len(INDICATORS))
