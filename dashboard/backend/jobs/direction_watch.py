"""복합 방향 전환 + 데이터 헬스 악화 감지 → 텔레그램 알림 메시지 생성.

매일 1회. 직전 상태(bot_state)와 비교해 '바뀐 순간만' 알린다.
macro_health()가 status와 복합 direction을 함께 주므로 한 번 호출로 둘 다 처리.
스펙: docs/SPEC_direction-health-alert.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.macro_health import macro_health

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
