"""매크로/9팩터 데이터 헬스 — 수집 신선도 + 복합 산출 가능 여부.

복합 방향(SPF·봇 리포트·리더보드 복합방향이 의존)이 조용히 neutral로 죽는 걸 감지.
스펙: docs/SPEC_macro-data-health.md
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone

import pandas as pd

_WARN_AGE_H = 30.0    # 일 1회 수집 기준 — 이 이상이면 주의
_STALE_AGE_H = 48.0   # 이 이상이면 수집 멈춤으로 간주
_MIN_FACTORS = 6      # 9팩터 중 최소 가용 수 (복합 신뢰 하한)


def macro_health(cache_path: str | None = None, today: date | None = None) -> dict:
    """매크로 캐시 신선도 + 소스별 최신성 + 복합 산출 가능 여부 → 헬스 dict."""
    cache_path = cache_path or os.getenv("MACRO_CACHE_PATH", "macro_cache.csv")
    today = today or datetime.now(timezone.utc).date()

    if not os.path.exists(cache_path):
        return {
            "status": "no_data",
            "cache_age_hours": None,
            "composite": None,
            "series": [],
            "message": "매크로 캐시 없음 — 아직 수집 전이거나 경로 불일치",
        }

    age_h = round((time.time() - os.path.getmtime(cache_path)) / 3600.0, 1)
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)

    # 소스별 최신성 (표시용)
    series = []
    for col in df.columns:
        s = df[col].dropna()
        last = s.index[-1].date() if len(s) else None
        series.append({
            "name": col,
            "last_date": last.isoformat() if last else None,
            "days_stale": (today - last).days if last else None,
        })

    # 복합 산출 가능 여부 (app.macro 재사용 — 런타임 sys.path)
    try:
        from app.macro.direction_composite import build_factors, latest_tilt
        tilt = latest_tilt(build_factors(**{c: df[c] for c in df.columns}))
        composite = {
            "direction": tilt.direction,
            "n_factors": tilt.n_factors,
            "composite_z": tilt.composite_z,
            "ok": tilt.n_factors >= _MIN_FACTORS,
        }
    except Exception as e:
        composite = {"direction": None, "n_factors": 0, "composite_z": None, "ok": False, "error": str(e)}

    comp_ok = bool(composite.get("ok"))
    if age_h > _STALE_AGE_H or not comp_ok:
        status = "stale"
    elif age_h > _WARN_AGE_H:
        status = "warn"
    else:
        status = "ok"

    return {"status": status, "cache_age_hours": age_h, "composite": composite, "series": series}
