"""SPF (Smart Position Flow) 서비스.

OI + FR 기반으로 포지션 흐름을 5종 분류하고,
코사인 유사도 패턴 매칭으로 3일 예측을 생성한다.
봇의 analysis_history에서 alert_level을 조회해 bearish_score를 보정한다.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)

# ── 포지션 흐름 분류 임계값 ────────────────────────────────────────
_OI_SURGE_THRESHOLD = 0.10   # OI 3일 변화율 +10% 이상 → 급등
_OI_DROP_THRESHOLD = -0.05   # OI 3일 변화율 -5% 이하 → 감소
_FR_HEAT_THRESHOLD = 0.02    # FR > 0.02% → 롱 과밀집
_FR_COOL_THRESHOLD = -0.01   # FR < -0.01% → 숏 과밀집


def classify_flow(oi_change_3d: float, cum_fr_3d: float) -> str:
    """5종 포지션 흐름 분류.

    Returns:
        'long_entry'  : OI↑ + FR↑ (롱 신규 진입)
        'short_entry' : OI↑ + FR↓ (숏 신규 진입)
        'long_exit'   : OI↓ + FR↑ (롱 청산)
        'short_exit'  : OI↓ + FR↓ (숏 청산)
        'neutral'     : 변동 미미
    """
    oi_up = oi_change_3d > _OI_SURGE_THRESHOLD
    oi_down = oi_change_3d < _OI_DROP_THRESHOLD
    fr_hot = cum_fr_3d > _FR_HEAT_THRESHOLD
    fr_cold = cum_fr_3d < _FR_COOL_THRESHOLD

    if oi_up and fr_hot:
        return "long_entry"
    if oi_up and fr_cold:
        return "short_entry"
    if oi_down and fr_hot:
        return "long_exit"
    if oi_down and fr_cold:
        return "short_exit"
    return "neutral"


def calc_bearish_score(
    oi_change_3d: float,
    oi_change_7d: float,
    cum_fr_3d: float,
    cum_fr_7d: float,
    oi_consecutive_up: int,
    flow: str,
    bot_alert_level: str | None = None,
) -> int:
    """하락 위험 점수 (0~100).

    봇의 alert_level로 +5~15 보정.
    """
    score = 0

    # OI 급등 위험
    if oi_change_3d > 0.20:
        score += 25
    elif oi_change_3d > 0.10:
        score += 15
    elif oi_change_3d > 0.05:
        score += 8

    # 7일 누적 OI
    if oi_change_7d > 0.30:
        score += 15
    elif oi_change_7d > 0.15:
        score += 8

    # FR 과열
    if cum_fr_3d > 0.05:
        score += 20
    elif cum_fr_3d > 0.02:
        score += 10
    elif cum_fr_3d > 0.01:
        score += 5

    # 7일 FR 누적
    if cum_fr_7d > 0.10:
        score += 10
    elif cum_fr_7d > 0.05:
        score += 5

    # 연속 OI 상승
    if oi_consecutive_up >= 5:
        score += 15
    elif oi_consecutive_up >= 3:
        score += 8

    # 흐름 가중치
    if flow == "long_entry":
        score += 5   # 과매수 위험
    elif flow == "short_exit":
        score -= 5   # 숏 청산 = 반등 신호

    # 봇 alert_level 보정
    if bot_alert_level == "EMERGENCY":
        score += 15
    elif bot_alert_level == "HIGH":
        score += 10
    elif bot_alert_level == "MEDIUM":
        score += 5

    return min(100, max(0, score))


def calc_bullish_score(
    oi_change_3d: float,
    cum_fr_3d: float,
    cum_fr_7d: float,
    flow: str,
    bot_alert_level: str | None = None,
) -> int:
    """반등 기대 점수 (0~100)."""
    score = 0

    # OI 감소 = 레버리지 해소
    if oi_change_3d < -0.10:
        score += 20
    elif oi_change_3d < -0.05:
        score += 10

    # FR 음수 = 숏 과밀집 (역발상 반등)
    if cum_fr_3d < -0.03:
        score += 25
    elif cum_fr_3d < -0.01:
        score += 12

    if cum_fr_7d < -0.05:
        score += 15
    elif cum_fr_7d < -0.02:
        score += 8

    # 흐름 가중치
    if flow == "short_entry":
        score += 10  # 숏 과밀집 = 반등 기대
    elif flow == "short_exit":
        score += 15  # 숏 청산 = 강한 반등 신호
    elif flow == "long_exit":
        score -= 5   # 롱 청산 = 하락 지속

    # 봇 alert_level (낮을수록 반등 여지)
    if bot_alert_level in (None, "NORMAL"):
        score += 5

    return min(100, max(0, score))


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """코사인 유사도."""
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _record_to_vector(r: dict) -> list[float]:
    """SPF 레코드를 코사인 유사도 계산용 벡터로 변환."""
    return [
        r.get("oi_change_3d") or 0,
        r.get("oi_change_7d") or 0,
        r.get("cum_fr_3d") or 0,
        r.get("cum_fr_7d") or 0,
        r.get("oi_change_14d") or 0,
        r.get("cum_fr_14d") or 0,
    ]


def find_similar_patterns(current: dict, top_n: int = 5) -> list[dict]:
    """현재 벡터와 가장 유사한 과거 패턴 TOP N 반환.

    완결된 패턴(price_after_3d 존재)만 대상으로 함.
    """
    current_vec = _record_to_vector(current)

    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, oi_change_3d, oi_change_7d, oi_change_14d,
                      cum_fr_3d, cum_fr_7d, cum_fr_14d,
                      price, price_after_3d, price_after_7d, flow, bearish_score
               FROM spf_records
               WHERE price_after_3d IS NOT NULL
               ORDER BY date DESC
               LIMIT 500"""
        ).fetchall()

    if not rows:
        return []

    scored = []
    for row in rows:
        d = dict(row)
        vec = _record_to_vector(d)
        sim = _cosine_similarity(current_vec, vec)
        if sim >= 0.85:
            price_then = d.get("price") or 0
            price_3d = d.get("price_after_3d") or 0
            change_3d = (price_3d - price_then) / price_then * 100 if price_then else 0
            scored.append({
                "date": d["date"],
                "similarity": round(sim * 100, 1),
                "flow": d.get("flow"),
                "change_3d_pct": round(change_3d, 2),
                "bearish_score": d.get("bearish_score"),
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_n]


def generate_prediction(
    bearish_score: int,
    bullish_score: int,
    similar_patterns: list[dict],
    flow: str,
    cum_fr_3d: float,
    oi_change_3d: float,
) -> dict:
    """3일 예측 방향 + 신뢰도 + 근거 생성."""

    # 패턴 기반 통계
    if similar_patterns:
        up_count = sum(1 for p in similar_patterns if p["change_3d_pct"] > 0)
        total = len(similar_patterns)
        pattern_up_prob = up_count / total * 100
    else:
        pattern_up_prob = 50.0

    # 점수 기반 방향
    score_diff = bearish_score - bullish_score
    if score_diff >= 20:
        direction = "하락"
        base_prob_down = min(75, 50 + score_diff)
    elif score_diff <= -20:
        direction = "상승"
        base_prob_down = max(25, 50 + score_diff)
    else:
        direction = "중립"
        base_prob_down = 50

    # 패턴 확률과 혼합 (가중치 6:4)
    final_down_prob = int(base_prob_down * 0.6 + (100 - pattern_up_prob) * 0.4)
    final_up_prob = 100 - final_down_prob

    # 신뢰도 = 두 신호의 일치도
    agreement = abs(base_prob_down - (100 - pattern_up_prob))
    confidence = max(50, min(85, 85 - agreement))

    # 방향 재결정
    if final_down_prob >= 55:
        direction = "하락"
    elif final_up_prob >= 55:
        direction = "상승"
    else:
        direction = "중립"

    # 근거 생성
    reasons = []
    if oi_change_3d > 0.10:
        reasons.append(f"OI 3일 +{oi_change_3d*100:.1f}% 급등 — 과매수 위험")
    elif oi_change_3d < -0.05:
        reasons.append(f"OI 3일 {oi_change_3d*100:.1f}% 감소 — 레버리지 해소")
    if cum_fr_3d > 0.02:
        reasons.append(f"FR 누적 {cum_fr_3d*100:.3f}% — 롱 과밀집")
    elif cum_fr_3d < -0.01:
        reasons.append(f"FR 누적 {cum_fr_3d*100:.3f}% — 숏 과밀집 (역발상)")
    flow_labels = {
        "long_entry": "롱 신규 진입 감지",
        "short_entry": "숏 신규 진입 감지",
        "long_exit": "롱 청산 진행 중",
        "short_exit": "숏 청산 진행 중",
        "neutral": "포지션 변동 미미",
    }
    reasons.append(flow_labels.get(flow, flow))
    if similar_patterns:
        reasons.append(
            f"유사 패턴 {len(similar_patterns)}건: 3일 후 상승 {int(pattern_up_prob)}% / 하락 {int(100-pattern_up_prob)}%"
        )

    return {
        "direction": direction,
        "confidence": int(confidence),
        "up_prob": final_up_prob,
        "down_prob": final_down_prob,
        "reasons": reasons,
    }


def get_bot_alert_level(symbol: str = "BTC/USDT") -> str | None:
    """봇 analysis_history에서 최신 alert_level 조회."""
    try:
        with get_db() as conn:
            row = conn.execute(
                """SELECT alert_level FROM analysis_history
                   WHERE symbol = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        return row["alert_level"] if row else None
    except Exception as e:
        logger.warning("봇 alert_level 조회 실패: %s", e)
        return None


def get_spf_data(limit: int = 90) -> list[dict]:
    """최근 SPF 레코드 조회."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM spf_records ORDER BY date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_spf() -> dict | None:
    """오늘 SPF 레코드 조회."""
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM spf_records WHERE date = ?", (today,)
        ).fetchone()
    return dict(row) if row else None


def get_prediction_history(limit: int = 30) -> list[dict]:
    """예측 기록 조회."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM predictions ORDER BY date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
