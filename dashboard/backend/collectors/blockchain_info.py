"""blockchain.info 공개 API — BTC 해시레이트 수집."""

from __future__ import annotations

import logging
import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://blockchain.info"


@cached(ttl=3600, key_prefix="btc_hashrate")
async def fetch_hashrate() -> dict | None:
    """BTC 네트워크 해시레이트 조회.

    Returns:
        {"hashrate_eh": float, "hashrate_raw": float}
        hashrate_eh: EH/s 단위 (엑사해시)
        hashrate_raw: blockchain.info 원본 값 (GH/s)
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_BASE}/q/hashrate")
            resp.raise_for_status()
            # 응답은 GH/s 단위 순수 숫자 텍스트
            raw = float(resp.text.strip())

        # GH/s → EH/s 변환 (1 EH = 10^9 GH)
        hashrate_eh = raw / 1_000_000_000

        return {
            "hashrate_eh": round(hashrate_eh, 2),
            "hashrate_raw_gh": raw,
        }
    except Exception as e:
        logger.error("BTC 해시레이트 조회 실패: %s", e)
        return None
