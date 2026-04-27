"""페이퍼 트레이딩 스코어카드 서비스.

정산 결과를 집계해 지표별·시장별 적중률 및 수익 현황을 반환한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard.backend.db.connection import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_iso(horizon_days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=horizon_days)
    return cutoff.isoformat()


def _safe_avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _hit_rate(hit_count: int, total: int) -> float:
    return hit_count / total * 100 if total > 0 else 0.0


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def get_scorecard(
    market: str | None = None,
    indicator: str | None = None,
    horizon_days: int | None = None,
) -> dict[str, Any]:
    """전체 스코어카드 집계.

    Args:
        market: 시장 필터 ('crypto' | 'kr_stock' | 'us_stock' | None).
        indicator: 지표 태그 필터 (e.g. 'OI', 'FR'). JSON indicator_tags 에 포함 여부 검사.
        horizon_days: 최근 N일 이내 정산 데이터만 집계.

    Returns:
        총 건수, 적중률, 평균 수익률 등을 담은 dict.
    """
    query = """
        SELECT
            ss.direction_hit,
            ss.price_error,
            ss.pnl_pct,
            ss.pnl,
            ss.liquidated,
            ss.settled_at,
            sp.indicator_tags,
            sa.market
        FROM sim_settlements ss
        JOIN sim_predictions sp ON ss.prediction_id = sp.id
        JOIN sim_accounts    sa ON sp.account_id    = sa.id
        WHERE ss.settled_at IS NOT NULL
    """
    params: list[Any] = []

    if market:
        query += " AND sa.market = ?"
        params.append(market)

    if horizon_days is not None:
        query += " AND ss.settled_at >= ?"
        params.append(_cutoff_iso(horizon_days))

    with get_db() as db:
        rows = db.execute(query, params).fetchall()

    # indicator 필터는 Python 단에서 수행 (JSON 파싱 필요)
    if indicator:
        filtered = []
        for row in rows:
            tags = _parse_tags(row["indicator_tags"])
            if indicator in tags:
                filtered.append(row)
        rows = filtered

    # --- 전체 집계 ---
    total_count = len(rows)
    hit_count = sum(1 for r in rows if r["direction_hit"] == 1)
    pnl_pct_list = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
    mae_list = [r["price_error"] for r in rows if r["price_error"] is not None]
    pnl_list = [r["pnl"] for r in rows if r["pnl"] is not None]
    liquidation_count = sum(1 for r in rows if r["liquidated"] == 1)

    # --- 시장별 집계 ---
    markets = ("crypto", "kr_stock", "us_stock")
    by_market: dict[str, dict[str, Any]] = {}
    for mkt in markets:
        mkt_rows = [r for r in rows if r["market"] == mkt]
        mkt_total = len(mkt_rows)
        mkt_hit = sum(1 for r in mkt_rows if r["direction_hit"] == 1)
        mkt_pnl_pct = [r["pnl_pct"] for r in mkt_rows if r["pnl_pct"] is not None]
        by_market[mkt] = {
            "count": mkt_total,
            "hit_rate": _hit_rate(mkt_hit, mkt_total),
            "avg_pnl_pct": _safe_avg(mkt_pnl_pct),
        }

    return {
        "total_count": total_count,
        "hit_count": hit_count,
        "hit_rate": _hit_rate(hit_count, total_count),
        "avg_pnl_pct": _safe_avg(pnl_pct_list),
        "avg_mae": _safe_avg(mae_list),
        "total_pnl": sum(pnl_list) if pnl_list else None,
        "liquidation_count": liquidation_count,
        "by_market": by_market,
    }


def get_scorecard_by_indicator(
    market: str | None = None,
    horizon_days: int | None = None,
) -> list[dict[str, Any]]:
    """지표 태그별 스코어카드 집계.

    각 지표 태그가 등장하는 정산 건에 대해 적중률과 평균 수익률을 계산한다.

    Args:
        market: 시장 필터.
        horizon_days: 최근 N일 이내 정산 데이터만 집계.

    Returns:
        지표별 집계 결과 리스트 (count DESC 정렬).
    """
    query = """
        SELECT
            ss.direction_hit,
            ss.pnl_pct,
            ss.settled_at,
            sp.indicator_tags,
            sa.market
        FROM sim_settlements ss
        JOIN sim_predictions sp ON ss.prediction_id = sp.id
        JOIN sim_accounts    sa ON sp.account_id    = sa.id
        WHERE ss.settled_at IS NOT NULL
    """
    params: list[Any] = []

    if market:
        query += " AND sa.market = ?"
        params.append(market)

    if horizon_days is not None:
        query += " AND ss.settled_at >= ?"
        params.append(_cutoff_iso(horizon_days))

    with get_db() as db:
        rows = db.execute(query, params).fetchall()

    # 지표별 데이터 누적
    indicator_map: dict[str, dict[str, Any]] = {}

    for row in rows:
        tags = _parse_tags(row["indicator_tags"])
        if not tags:
            # indicator_tags 가 비어 있으면 지표 집계에서 제외
            continue

        for tag in tags:
            if tag not in indicator_map:
                indicator_map[tag] = {"hit_list": [], "pnl_pct_list": [], "count": 0}

            entry = indicator_map[tag]
            entry["count"] += 1
            if row["direction_hit"] == 1:
                entry["hit_list"].append(1)
            if row["pnl_pct"] is not None:
                entry["pnl_pct_list"].append(row["pnl_pct"])

    # 결과 변환
    result: list[dict[str, Any]] = []
    for tag, data in indicator_map.items():
        count = data["count"]
        hit_count = len(data["hit_list"])
        result.append({
            "indicator": tag,
            "count": count,
            "hit_count": hit_count,
            "hit_rate": _hit_rate(hit_count, count),
            "avg_pnl_pct": _safe_avg(data["pnl_pct_list"]),
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _parse_tags(raw: str | None) -> list[str]:
    """indicator_tags JSON 문자열을 파싱해 리스트로 반환.

    파싱 실패 또는 None 이면 빈 리스트 반환.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t) for t in parsed if t]
        return []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
