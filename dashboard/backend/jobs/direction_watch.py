"""복합 방향 전환 + 데이터 헬스 악화 + 반도체 시그널 stale 감지 → 텔레그램 알림 메시지 생성.

매일 1회. 직전 상태(bot_state)와 비교해 '바뀐 순간만' 알린다.
macro_health()가 status와 복합 direction을 함께 주므로 한 번 호출로 둘 다 처리.
스펙: docs/SPEC_direction-health-alert.md, docs/plans/semiconductor-peak-card-2026-07-04.md
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.macro_health import macro_health
from dashboard.backend.services.research_analyzer import semiconductor_stale_status

logger = logging.getLogger(__name__)

_DIR_KR = {"long": "강세", "short": "약세", "neutral": "중립"}
_BAD = {"stale", "no_data"}


def _get_state(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_state(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now),
        )


def check_direction_and_health(health: dict | None = None) -> list[str]:
    """직전 상태 대비 방향 전환·헬스 악화 감지 → 발송 메시지 리스트.

    health 주입 가능(테스트용). 미주입 시 macro_health() 호출.
    """
    if health is None:
        health = macro_health()
    msgs: list[str] = []

    # 1) 데이터 헬스 악화 — 정상→비정상 전이에서만 1회
    status = health.get("status")
    prev_status = _get_state("health_status")
    if status in _BAD and prev_status not in _BAD:
        age = health.get("cache_age_hours")
        msgs.append(
            "⚠️ <b>데이터 상태 경고</b>\n"
            f"방향 모델 입력이 비정상입니다 (상태: {status}"
            + (f", 마지막 수집 {age}시간 전" if age is not None else "")
            + ").\n복합 방향 신호를 신뢰할 수 없습니다 — 수집 점검 필요."
        )
    _set_state("health_status", status or "unknown")

    # 2) 복합 방향 전환 — 헬스 정상(복합 산출 가능)일 때만
    comp = health.get("composite") or {}
    if comp.get("ok"):
        cur = comp.get("direction")
        prev = _get_state("composite_direction")
        if prev and cur and prev != cur:
            z = comp.get("composite_z")
            msgs.append(
                "🧭 <b>시장 방향 전환</b>\n"
                f"{_DIR_KR.get(prev, prev)} → <b>{_DIR_KR.get(cur, cur)}</b>"
                + (f" (복합 z {z:+.2f})" if z is not None else "")
                + "\n9팩터 복합 중기(주 단위) 방향이 전환됐습니다."
            )
        if cur:
            _set_state("composite_direction", cur)

    return msgs


_SEMI_STALE_KEY = "semiconductor_peak_stale_alerted"


def _stale_message(s: dict) -> str:
    return (
        "🔺 <b>반도체 정점 카드 갱신 필요</b>\n"
        f"마지막 확인: {s['as_of']} ({s['days_since']}일 전 · 기준 {s['threshold_days']}일 초과)\n"
        f"현재 정점 임박 {s['peak_count']}/{s['total']} (level: {s['level']})\n"
        "Claude에게 '반도체 시그널 갱신'을 요청하세요."
    )


def _save_stale_alert(s: dict) -> None:
    details = json.dumps(
        {k: s[k] for k in ("as_of", "days_since", "threshold_days", "peak_count", "total", "level")},
        ensure_ascii=False,
    )
    with get_db() as conn:
        conn.execute(
            "INSERT INTO alert_history (symbol, alert_level, details) VALUES (?, ?, ?)",
            ("반도체", "STALE_SIGNAL", details),
        )


def check_semiconductor_stale(status: dict | None = None) -> list[str]:
    """반도체 시그널 데이터가 stale로 '전이'된 순간에만 갱신 알림.

    status 주입 가능(테스트용). 미주입 시 semiconductor_stale_status() 호출.
    stale→ok 복구 시 상태를 리셋해 다음 stale 때 재알림한다.
    """
    if status is None:
        status = semiconductor_stale_status()
    msgs: list[str] = []

    prev = _get_state(_SEMI_STALE_KEY)  # 이미 알렸으면 "1"
    if status["is_stale"]:
        if prev != "1":
            _save_stale_alert(status)
            msgs.append(_stale_message(status))
            _set_state(_SEMI_STALE_KEY, "1")
    elif prev == "1":
        _set_state(_SEMI_STALE_KEY, "0")  # 복구 → 리셋

    return msgs


# ── TGA(재무부 일반계정) 급변 이벤트 알림 ────────────────────
# 임계 T: 캘리브레이션 2026-07-04 (docs/TGA_calibration_2026-07-04.md).
# WTREGEN 5.5년 non-overlapping 4주 블록 + 히스테리시스 상태머신 시뮬 → 연 6회 발화.
_TGA_THRESHOLD = 120_000     # 백만$ ($120B). 4주 변화 |Δ| 이 값 돌파 시 알림
_TGA_RESET_RATIO = 0.7       # |Δ| < 0.7T 복귀 시 상태 리셋(재발화 진동 방지)
_TGA_STATE_KEY = "tga_4w_alert_state"  # neutral / above_positive / above_negative


def _current_tga_delta_4w() -> float | None:
    """매크로 캐시의 tga 컬럼에서 4주(28일) 변화 산출. 캐시/컬럼 부재·이력부족 시 None."""
    import pandas as pd
    cache_path = os.getenv("MACRO_CACHE_PATH", "macro_cache.csv")
    if not os.path.exists(cache_path):
        return None
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    if "tga" not in df.columns:
        return None
    tga = df["tga"].dropna()
    if len(tga) < 29:  # 28일 전 값 필요
        return None
    return float(tga.iloc[-1] - tga.iloc[-29])


def _tga_message(delta_4w: float, direction: str) -> str:
    b = abs(delta_4w) / 1000  # 백만$ → $B
    if direction == "increase":
        return (
            f"💧 <b>TGA 4주 +${b:,.0f}B 급증</b>\n"
            "재무부 유동성 흡수 국면 — 순유동성 압박(약세 압력)"
        )
    return (
        f"💧 <b>TGA 4주 −${b:,.0f}B 급감</b>\n"
        "재무부 유동성 방출 — 완화 국면"
    )


def _save_tga_alert(delta_4w: float, direction: str) -> None:
    details = json.dumps(
        {"delta_4w": round(delta_4w), "threshold": _TGA_THRESHOLD, "direction": direction},
        ensure_ascii=False,
    )
    with get_db() as conn:
        conn.execute(
            "INSERT INTO alert_history (symbol, alert_level, details) VALUES (?, ?, ?)",
            ("TGA", "MACRO_EVENT", details),
        )


def check_tga_event(delta_4w: float | None = None) -> list[str]:
    """TGA 4주 변화가 임계 상태로 '전이'된 순간에만 알림 (3상태 히스테리시스).

    delta_4w 주입 가능(테스트용). 미주입 시 매크로 캐시에서 산출.
    전이: neutral→above_±(발화), above_+↔above_−(방향전환 발화),
    above_±→neutral(|Δ|<0.7T, 무발화 리셋). 동일 상태 유지 시 무발화.
    """
    if delta_4w is None:
        delta_4w = _current_tga_delta_4w()
    if delta_4w is None:
        return []

    T, reset = _TGA_THRESHOLD, _TGA_RESET_RATIO * _TGA_THRESHOLD
    prev = _get_state(_TGA_STATE_KEY) or "neutral"
    new_state = prev

    if prev == "neutral":
        if delta_4w >= T:
            new_state = "above_positive"
        elif delta_4w <= -T:
            new_state = "above_negative"
    elif prev == "above_positive":
        if delta_4w <= -T:
            new_state = "above_negative"
        elif abs(delta_4w) < reset:
            new_state = "neutral"
    else:  # above_negative
        if delta_4w >= T:
            new_state = "above_positive"
        elif abs(delta_4w) < reset:
            new_state = "neutral"

    msgs: list[str] = []
    if new_state != prev:
        _set_state(_TGA_STATE_KEY, new_state)
        if new_state in ("above_positive", "above_negative"):
            direction = "increase" if new_state == "above_positive" else "decrease"
            _save_tga_alert(delta_4w, direction)
            msgs.append(_tga_message(delta_4w, direction))

    return msgs
