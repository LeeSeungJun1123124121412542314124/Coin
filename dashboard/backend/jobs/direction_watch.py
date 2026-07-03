"""복합 방향 전환 + 데이터 헬스 악화 + 반도체 시그널 stale 감지 → 텔레그램 알림 메시지 생성.

매일 1회. 직전 상태(bot_state)와 비교해 '바뀐 순간만' 알린다.
macro_health()가 status와 복합 direction을 함께 주므로 한 번 호출로 둘 다 처리.
스펙: docs/SPEC_direction-health-alert.md, docs/plans/semiconductor-peak-card-2026-07-04.md
"""

from __future__ import annotations

import json
import logging
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
