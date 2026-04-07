"""Hyperliquid 공개 API 수집기 — 고래 리더보드 + 포지션.

키 불필요 (공개 API).
엔드포인트: https://api.hyperliquid.xyz/info
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_BASE = "https://api.hyperliquid.xyz/info"
_HEADERS = {"Content-Type": "application/json"}


async def _post(payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_BASE, json=payload, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


@cached(120, "hl_leaderboard")
async def fetch_leaderboard(top_n: int = 20) -> list[dict]:
    """Hyperliquid 리더보드 TOP N.

    Returns list of:
      {rank, address, display_name, account_value, pnl_30d, roi_30d, volume_30d}
    """
    try:
        data = await _post({
            "type": "leaderboard",
            "req": {
                "timeWindow": "month",
            },
        })

        leaderboard = data if isinstance(data, list) else data.get("leaderboardRows", [])
        if not leaderboard:
            # 구조 변경에 대비한 폴백
            leaderboard = data.get("rows", [])

        result = []
        for i, row in enumerate(leaderboard[:top_n]):
            # HL API 응답 구조 처리
            account_value = _safe_float(
                row.get("accountValue") or row.get("equity") or row.get("value")
            )
            pnl = _safe_float(
                row.get("pnl") or row.get("pnl30d") or row.get("monthlyPnl")
            )
            roi = _safe_float(
                row.get("roi") or row.get("roi30d") or row.get("monthlyRoi")
            )
            volume = _safe_float(
                row.get("volume") or row.get("volume30d") or row.get("monthlyVolume")
            )

            result.append({
                "rank": i + 1,
                "address": row.get("ethAddress") or row.get("address") or "",
                "display_name": row.get("displayName") or row.get("nickname") or None,
                "account_value": account_value,
                "pnl_30d": pnl,
                "roi_30d": roi,
                "volume_30d": volume,
            })

        return result

    except Exception as e:
        logger.error("HL 리더보드 조회 실패: %s", e)
        return []


@cached(120, "hl_positions")
async def fetch_user_positions(address: str) -> dict | None:
    """특정 주소의 현재 포지션 + 계좌 상태.

    Returns:
      {address, account_value, unrealized_pnl, positions: [...]}
    """
    try:
        data = await _post({
            "type": "clearinghouseState",
            "user": address,
        })

        margin_summary = data.get("marginSummary", {})
        account_value = _safe_float(margin_summary.get("accountValue"))
        unrealized_pnl = _safe_float(margin_summary.get("totalUnrealizedPnl"))

        positions = []
        for pos in data.get("assetPositions", []):
            p = pos.get("position", {})
            coin = p.get("coin", "")
            size = _safe_float(p.get("szi"))
            entry_px = _safe_float(p.get("entryPx"))
            unrealized = _safe_float(p.get("unrealizedPnl"))
            leverage = p.get("leverage", {})
            lev_value = _safe_float(leverage.get("value") if isinstance(leverage, dict) else leverage)

            if size == 0:
                continue

            positions.append({
                "coin": coin,
                "size": size,
                "side": "long" if (size or 0) > 0 else "short",
                "entry_px": entry_px,
                "unrealized_pnl": unrealized,
                "leverage": lev_value,
            })

        return {
            "address": address,
            "account_value": account_value,
            "unrealized_pnl": unrealized_pnl,
            "positions": positions,
        }

    except Exception as e:
        logger.error("HL 포지션 조회 실패 (%s): %s", address, e)
        return None


async def fetch_top_whale_positions(top_n: int = 10) -> list[dict]:
    """리더보드 TOP N의 포지션을 병렬 조회."""
    leaderboard = await fetch_leaderboard(top_n)
    if not leaderboard:
        return []

    tasks = [fetch_user_positions(w["address"]) for w in leaderboard]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    whales = []
    for whale_meta, pos_data in zip(leaderboard, results):
        if isinstance(pos_data, Exception) or pos_data is None:
            pos_data = {"positions": [], "account_value": whale_meta.get("account_value"), "unrealized_pnl": None}

        whales.append({
            **whale_meta,
            "unrealized_pnl": pos_data.get("unrealized_pnl"),
            "positions": pos_data.get("positions", []),
        })

    return whales


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
