"""김치 프리미엄 수집 작업 — 2시간마다 DB에 저장."""

from __future__ import annotations

import logging

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.kimchi_premium import calc_kimchi_premium
from dashboard.backend.collectors.coinbase import fetch_btc_usd

logger = logging.getLogger(__name__)


async def collect_kimchi() -> None:
    """현재 김치 프리미엄 계산 후 kimchi_premium_history 테이블에 저장."""
    try:
        btc_usd = await fetch_btc_usd()
        if btc_usd is None:
            logger.warning("BTC USD 가격 조회 실패 — 김프 수집 스킵")
            return

        result = await calc_kimchi_premium(btc_usd)
        if result is None:
            logger.warning("김치 프리미엄 계산 실패 — 스킵")
            return

        with get_db() as conn:
            conn.execute(
                """INSERT INTO kimchi_premium_history
                   (btc_krw, btc_usd, usd_krw, premium_pct)
                   VALUES (?, ?, ?, ?)""",
                (
                    result["upbit_btc_krw"],
                    btc_usd,
                    result["usd_krw"],
                    result["kimchi_premium_pct"],
                ),
            )
        logger.info("김치 프리미엄 저장 완료: %.2f%%", result["kimchi_premium_pct"])
    except Exception as e:
        logger.error("김치 프리미엄 수집 실패: %s", e, exc_info=True)
