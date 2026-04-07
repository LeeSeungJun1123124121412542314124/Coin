"""SPF API 라우터 — 탭 3 포지션 흐름 분석."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.bybit_derivatives import (
    fetch_open_interest,
    fetch_funding_rate,
)
from dashboard.backend.services.spf_service import (
    classify_flow,
    calc_bearish_score,
    calc_bullish_score,
    find_similar_patterns,
    generate_prediction,
    get_bot_alert_level,
    get_spf_data,
    get_today_spf,
    get_prediction_history,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/spf-data")
async def get_spf():
    """SPF 현재 상태 + 최근 90일 히스토리."""
    today_record = get_today_spf()
    history = get_spf_data(90)

    # 오늘 레코드 없으면 실시간 계산
    current = today_record
    if current is None:
        current = await _calc_realtime_spf()

    spf_message = None
    if current is None:
        spf_message = (
            "SPF 현재 데이터 없음 — OI/FR API 실패 또는 DB 미수집입니다. "
            "잠시 후 새로고침하거나 POST /api/spf-refresh 로 갱신해 보세요."
        )

    # 유사 패턴 TOP5
    similar = find_similar_patterns(current) if current else []

    # 오늘 예측
    from dashboard.backend.services.spf_service import get_prediction_history as get_preds
    from dashboard.backend.db.connection import get_db
    import datetime
    today_str = datetime.date.today().isoformat()
    with get_db() as conn:
        today_pred = conn.execute(
            "SELECT * FROM predictions WHERE date = ?", (today_str,)
        ).fetchone()
    today_pred = dict(today_pred) if today_pred else None

    return JSONResponse({
        "current": current,
        "history": history,
        "similar_patterns": similar,
        "today_prediction": today_pred,
        "message": spf_message,
    })


@router.get("/prediction-history")
async def get_pred_history():
    """예측 기록 + 누적 적중률."""
    history = get_prediction_history(30)

    # 적중률 계산
    judged = [p for p in history if p.get("result") in ("hit", "miss")]
    hits = sum(1 for p in judged if p["result"] == "hit")
    accuracy = round(hits / len(judged) * 100, 1) if judged else None

    return JSONResponse({
        "predictions": history,
        "stats": {
            "total": len(judged),
            "hits": hits,
            "accuracy_pct": accuracy,
        },
    })


@router.post("/spf-refresh")
async def refresh_spf():
    """SPF 데이터 강제 갱신 (수동 트리거)."""
    from dashboard.backend.jobs.collect_spf import collect_spf
    await collect_spf()
    return JSONResponse({"ok": True, "message": "SPF 갱신 완료"})


async def _calc_realtime_spf() -> dict | None:
    """오늘 레코드 없을 때 실시간으로 계산."""
    from dashboard.backend.collectors.bybit_derivatives import (
        fetch_oi_history, fetch_fr_history,
    )

    oi_hist, fr_hist, oi_now, fr_now = await asyncio.gather(
        fetch_oi_history("BTCUSDT", limit=20),
        fetch_fr_history("BTCUSDT", limit=45),
        fetch_open_interest("BTCUSDT"),
        fetch_funding_rate("BTCUSDT"),
        return_exceptions=True,
    )

    if isinstance(oi_hist, Exception):
        logger.error("SPF 실시간 OI 히스토리 실패: %s", oi_hist, exc_info=oi_hist)
        return None
    if not oi_hist:
        logger.warning("SPF 실시간 OI 히스토리 비어 있음")
        return None
    if isinstance(fr_hist, Exception):
        logger.error("SPF 실시간 FR 히스토리 실패: %s", fr_hist, exc_info=fr_hist)
    if isinstance(oi_now, Exception):
        logger.error("SPF 실시간 OI 현재값 실패: %s", oi_now, exc_info=oi_now)
    if isinstance(fr_now, Exception):
        logger.error("SPF 실시간 FR 현재값 실패: %s", fr_now, exc_info=fr_now)

    oi_hist = sorted(oi_hist, key=lambda x: x["timestamp"])
    latest_oi = oi_hist[-1]["open_interest"] if oi_hist else None
    if not latest_oi:
        return None

    def oi_change(days: int) -> float:
        if len(oi_hist) <= days:
            return 0.0
        past = oi_hist[-days - 1]["open_interest"]
        return (latest_oi - past) / past if past else 0.0

    oi_c3d = oi_change(3)
    oi_c7d = oi_change(7)
    oi_c14d = oi_change(14)

    if not isinstance(fr_hist, Exception) and fr_hist:
        fr_hist = sorted(fr_hist, key=lambda x: x["timestamp"])
        cum_fr_3d = sum(r["funding_rate"] for r in fr_hist[-9:])
        cum_fr_7d = sum(r["funding_rate"] for r in fr_hist[-21:])
        cum_fr_14d = sum(r["funding_rate"] for r in fr_hist[-42:])
        latest_fr = fr_hist[-1]["funding_rate"] if fr_hist else None
    else:
        cum_fr_3d = cum_fr_7d = cum_fr_14d = 0.0
        latest_fr = None

    consecutive_up = 0
    for i in range(len(oi_hist) - 1, 0, -1):
        if oi_hist[i]["open_interest"] > oi_hist[i - 1]["open_interest"]:
            consecutive_up += 1
        else:
            break

    flow = classify_flow(oi_c3d, cum_fr_3d)
    bot_level = get_bot_alert_level("BTC/USDT")
    bearish = calc_bearish_score(oi_c3d, oi_c7d, cum_fr_3d, cum_fr_7d, consecutive_up, flow, bot_level)
    bullish = calc_bullish_score(oi_c3d, cum_fr_3d, cum_fr_7d, flow, bot_level)

    return {
        "date": "realtime",
        "oi": latest_oi,
        "fr": latest_fr,
        "price": None,
        "oi_change_3d": oi_c3d,
        "oi_change_7d": oi_c7d,
        "oi_change_14d": oi_c14d,
        "cum_fr_3d": cum_fr_3d,
        "cum_fr_7d": cum_fr_7d,
        "cum_fr_14d": cum_fr_14d,
        "flow": flow,
        "bearish_score": bearish,
        "bullish_score": bullish,
        "oi_consecutive_up": consecutive_up,
        "oi_surge_alert": "CRITICAL" if oi_c3d > 0.20 else "WARNING" if oi_c3d > 0.10 else None,
    }
