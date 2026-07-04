"""SPF 데이터 수집 — 매일 00:10 UTC.

Bybit에서 OI/FR/BTC 가격을 수집하여 spf_records에 저장하고,
당일 예측도 생성하여 predictions에 저장한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date

from dashboard.backend.utils.retry import async_retry
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.collectors.bybit_derivatives import (
    fetch_oi_history,
    fetch_fr_history,
)
from dashboard.backend.db.connection import get_db
from dashboard.backend.services.spf_service import (
    classify_flow,
    calc_bearish_score,
    calc_bullish_score,
    composite_prediction,
    find_similar_patterns,
)

logger = logging.getLogger(__name__)


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_spf() -> None:
    """OI/FR/BTC 일별 레코드 수집 및 저장, 예측 생성."""
    logger.info("SPF 수집 시작")

    try:
        oi_hist, fr_hist = await asyncio.gather(
            fetch_oi_history("BTCUSDT", limit=30),
            fetch_fr_history("BTCUSDT", limit=90),
            return_exceptions=True,
        )
        if isinstance(oi_hist, Exception):
            oi_hist = None
        if isinstance(fr_hist, Exception):
            fr_hist = None
    except Exception as e:
        logger.error("SPF 데이터 수집 실패: %s", e)
        raise  # 예외 전파 — decorator가 재시도

    if not oi_hist or not fr_hist:
        logger.warning("SPF 데이터 없음")
        return

    # OI 히스토리 날짜별 정렬 (오래된 순)
    oi_hist.sort(key=lambda x: x["timestamp"])
    # FR 히스토리 날짜별 정렬
    fr_hist.sort(key=lambda x: x["timestamp"])

    # 오늘 날짜
    today = date.today().isoformat()

    # 최신 OI
    latest_oi = oi_hist[-1]["open_interest"] if oi_hist else None
    if latest_oi is None:
        return

    # OI 변화율 계산
    def oi_change(days: int) -> float:
        if len(oi_hist) <= days:
            return 0.0
        past = oi_hist[-days - 1]["open_interest"]
        return (latest_oi - past) / past if past else 0.0

    oi_c3d = oi_change(3)
    oi_c7d = oi_change(7)
    oi_c14d = oi_change(14)

    # FR 누적 계산 (최근 N일 * 3건/일)
    def cum_fr(days: int) -> float:
        recent = fr_hist[-(days * 3):]
        return sum(r["funding_rate"] for r in recent)

    cum_fr_3d = cum_fr(3)
    cum_fr_7d = cum_fr(7)
    cum_fr_14d = cum_fr(14)

    # 연속 OI 상승일 수
    consecutive_up = 0
    for i in range(len(oi_hist) - 1, 0, -1):
        if oi_hist[i]["open_interest"] > oi_hist[i - 1]["open_interest"]:
            consecutive_up += 1
        else:
            break

    # BTC 가격 (봇 DataCollector 재활용)
    btc_price = await _get_btc_price()

    # 포지션 흐름 분류 (정보 뷰용)
    flow = classify_flow(oi_c3d, cum_fr_3d)

    # 점수 계산 (정보 뷰용 — 방향 결정엔 미사용. 봇 alert_level 보정 제거)
    bearish = calc_bearish_score(oi_c3d, oi_c7d, cum_fr_3d, cum_fr_7d, consecutive_up, flow, None)
    bullish = calc_bullish_score(oi_c3d, cum_fr_3d, cum_fr_7d, flow, None)

    # OI 급등 경고
    oi_surge = "CRITICAL" if oi_c3d > 0.20 else "WARNING" if oi_c3d > 0.10 else None

    # DB 저장
    record = {
        "date": today,
        "oi": latest_oi,
        "fr": fr_hist[-1]["funding_rate"] if fr_hist else None,
        "price": btc_price,
        "oi_change_3d": oi_c3d,
        "oi_change_7d": oi_c7d,
        "oi_change_14d": oi_c14d,
        "price_change_3d": None,  # 3일 후 업데이트
        "cum_fr_3d": cum_fr_3d,
        "cum_fr_7d": cum_fr_7d,
        "cum_fr_14d": cum_fr_14d,
        "flow": flow,
        "bearish_score": bearish,
        "bullish_score": bullish,
        "oi_consecutive_up": consecutive_up,
        "oi_surge_alert": oi_surge,
    }

    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO spf_records
               (date, oi, fr, price, oi_change_3d, oi_change_7d, oi_change_14d,
                price_change_3d, cum_fr_3d, cum_fr_7d, cum_fr_14d,
                flow, bearish_score, bullish_score, oi_consecutive_up, oi_surge_alert)
               VALUES (:date, :oi, :fr, :price, :oi_change_3d, :oi_change_7d, :oi_change_14d,
                       :price_change_3d, :cum_fr_3d, :cum_fr_7d, :cum_fr_14d,
                       :flow, :bearish_score, :bullish_score, :oi_consecutive_up, :oi_surge_alert)""",
            record,
        )

    logger.info("SPF 레코드 저장: %s | 하락%d 반등%d | %s", today, bearish, bullish, flow)

    # 예측 생성 및 저장 (방향은 복합 모델, OI/FR은 정보 뷰)
    tilt = _compute_tilt()
    await _save_prediction(today, record, tilt)


def _compute_tilt():
    """9팩터 복합 시장방향 tilt 계산 (실패 시 None — 방향 없이 폴백).

    매크로 소스 일 1회 캐시(get_sources) 재사용. app.macro는 런타임 sys.path로 임포트.
    """
    import os
    try:
        from app.macro.collectors import get_sources
        from app.macro.direction_composite import build_factors, latest_tilt
        sources = get_sources(os.getenv("MACRO_CACHE_PATH", "macro_cache.csv"))
        return latest_tilt(build_factors(**sources))
    except Exception as e:
        logger.warning("복합 tilt 계산 실패 (방향 없이 저장): %s", e)
        return None


async def _save_prediction(today: str, record: dict, tilt) -> None:
    """오늘 예측을 predictions 테이블에 저장. 방향=복합 tilt, top_patterns=OI/FR 유사패턴(뷰)."""
    similar = find_similar_patterns(record)
    pred = composite_prediction(tilt)

    # 근거: 복합 상위 기여 팩터 + 포지션 흐름 라벨
    reasons = []
    if tilt is not None and getattr(tilt, "contributions", None):
        top = sorted(tilt.contributions.items(), key=lambda kv: -abs(kv[1]))[:3]
        reasons += [f"{k} {v:+.2f}" for k, v in top]
    flow_labels = {
        "long_entry": "롱 신규 진입", "short_entry": "숏 신규 진입",
        "long_exit": "롱 청산", "short_exit": "숏 청산", "neutral": "포지션 변동 미미",
    }
    reasons.append(flow_labels.get(record["flow"], record["flow"]))

    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO predictions
               (date, direction, confidence, bullish_score, bearish_score,
                up_prob, down_prob, top_patterns, reasons)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                today,
                pred["direction"],
                pred["confidence"],
                record["bullish_score"],
                record["bearish_score"],
                pred["up_prob"],
                pred["down_prob"],
                json.dumps(similar, ensure_ascii=False),
                json.dumps(reasons, ensure_ascii=False),
            ),
        )
    logger.info("예측 저장: %s | %s (%d%%, z=%s)", today, pred["direction"], pred["confidence"], pred["composite_z"])


async def _get_btc_price() -> float | None:
    """봇 DataCollector로 BTC 현재가 조회."""
    import asyncio
    from app.data.data_collector import DataCollector

    loop = asyncio.get_running_loop()
    try:
        collector = DataCollector()
        ohlcv = await loop.run_in_executor(None, collector.fetch_ohlcv, "BTC/USDT", "1d", 1)
        if ohlcv is not None and len(ohlcv) > 0:
            return float(ohlcv["close"].iloc[-1])
    except Exception as e:
        logger.error("BTC 가격 조회 실패: %s", e)
    return None
