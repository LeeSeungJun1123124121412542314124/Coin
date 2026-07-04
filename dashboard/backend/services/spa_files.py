"""SPA 정적 파일 서빙의 경로 판정 — 경로 탐색(path traversal) 차단.

catch-all 라우트는 무인증이므로 dist 밖 파일(.env, DB 등) 노출을 반드시 막아야 함.
docs/plans/fix-review-3items-2026-07-04.md #1
"""

from __future__ import annotations

from pathlib import Path


def safe_static_file(dist: Path, full_path: str) -> Path | None:
    """dist 하위의 실존 파일만 반환 — 상위 디렉터리 탈출·절대경로는 None."""
    try:
        candidate = (dist / full_path).resolve()
    except (OSError, ValueError):  # Windows 금지 문자 등 resolve 실패
        return None
    if candidate.is_file() and candidate.is_relative_to(dist.resolve()):
        return candidate
    return None
