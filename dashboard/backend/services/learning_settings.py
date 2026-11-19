"""학습 탭 설정 — learning_settings 테이블(key별 JSON), 기본값과 깊은 병합 + 범위 검증."""

from __future__ import annotations

import copy
import json
import math

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_indicators import INTERVALS


class LearningError(ValueError):
    """학습 탭 입력 검증 실패 (HTTP 400으로 변환)."""


DEFAULTS = {
    "wyckoff": {"n": 30, "width_pct": 15.0, "vol_mult": 2.0},
    "elliott": {"threshold_1h": 3.0, "threshold_4h": 5.0, "threshold_1d": 10.0,
                "threshold_1w": 20.0, "threshold_1M": 30.0, "levels": [0.382, 0.5, 0.618, 1.0, 1.618]},
    "dca": {"symbol": "BTCUSDT"},
    "indicators": {
        "ma": {"enabled": False, "type": "sma", "periods": [5, 20, 60, 120]},
        "bb": {"enabled": False, "period": 20, "stddev": 2.0},
        "volume": {"enabled": False},
        "rsi": {"enabled": False, "period": 14},
        "macd": {"enabled": False, "fast": 12, "slow": 26, "signal": 9},
    },
}


def _merge(base: dict, patch: dict) -> dict:
    """patch를 base 위에 깊은 병합 (base 불변)."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_range(name: str, v, lo: float, hi: float) -> None:
    if not _is_num(v) or not lo <= v <= hi:
        raise LearningError(f"{name}은(는) {lo}~{hi} 범위의 숫자여야 합니다.")


def _check_int(name: str, v, lo: int, hi: int) -> None:
    """lo~hi 범위의 정수(bool 제외)인지 검사."""
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise LearningError(f"{name}은(는) {lo}~{hi} 범위의 정수여야 합니다.")


def _validate_indicators(ind: dict) -> None:
    for key in ("ma", "bb", "volume", "rsi", "macd"):
        if not isinstance(ind[key]["enabled"], bool):
            raise LearningError(f"indicators.{key}.enabled은(는) 참/거짓이어야 합니다.")
    ma = ind["ma"]
    if ma["type"] not in ("sma", "ema"):
        raise LearningError("indicators.ma.type은(는) sma 또는 ema여야 합니다.")
    ps = ma["periods"]
    if not isinstance(ps, list) or not 1 <= len(ps) <= 6:
        raise LearningError("indicators.ma.periods는 1~6개의 목록이어야 합니다.")
    for p in ps:
        _check_int("indicators.ma.periods", p, 2, 400)
    _check_int("indicators.bb.period", ind["bb"]["period"], 5, 200)
    _check_range("indicators.bb.stddev", ind["bb"]["stddev"], 0.5, 4)
    _check_int("indicators.rsi.period", ind["rsi"]["period"], 2, 100)
    m = ind["macd"]
    _check_int("indicators.macd.fast", m["fast"], 2, 200)
    _check_int("indicators.macd.slow", m["slow"], 3, 400)
    _check_int("indicators.macd.signal", m["signal"], 2, 100)
    if m["fast"] >= m["slow"]:
        raise LearningError("indicators.macd.fast는 slow보다 작아야 합니다.")


def _validate(s: dict) -> None:
    w, e, d = s["wyckoff"], s["elliott"], s["dca"]
    _check_range("wyckoff.n", w["n"], 5, 200)
    if not isinstance(w["n"], int):
        raise LearningError("wyckoff.n은(는) 정수여야 합니다.")
    _check_range("wyckoff.width_pct", w["width_pct"], 1, 100)
    _check_range("wyckoff.vol_mult", w["vol_mult"], 1, 10)
    for iv in INTERVALS:
        _check_range(f"elliott.threshold_{iv}", e[f"threshold_{iv}"], 1, 50)
    lv = e["levels"]
    if not isinstance(lv, list) or not 1 <= len(lv) <= 10 or not all(_is_num(x) and x > 0 for x in lv):
        raise LearningError("elliott.levels는 양수 1~10개의 목록이어야 합니다.")
    if not isinstance(d["symbol"], str) or not d["symbol"]:
        raise LearningError("dca.symbol은 비어 있지 않은 문자열이어야 합니다.")
    _validate_indicators(s["indicators"])


def get_settings() -> dict:
    """저장된 설정을 기본값과 병합해 반환."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM learning_settings").fetchall()
    stored = {r[0]: json.loads(r[1]) for r in rows}
    return _merge(DEFAULTS, {k: v for k, v in stored.items() if k in DEFAULTS})


def update_settings(patch: dict) -> dict:
    """부분 patch를 병합·전체 검증 후 저장. 위반 시 LearningError."""
    merged = _merge(get_settings(), {k: v for k, v in patch.items() if k in DEFAULTS})
    _validate(merged)
    # dca.symbol은 patch에서 바꿀 때만 추적 종목 여부 검증 (기본값 BTCUSDT는 미추적 상태에서도 허용)
    if "symbol" in (patch.get("dca") or {}):
        from dashboard.backend.services.learning_symbols import list_symbols  # 순환 import 회피
        if merged["dca"]["symbol"] not in {x["symbol"] for x in list_symbols()}:
            raise LearningError("dca.symbol은 추적 중인 종목이어야 합니다.")
    with get_db() as conn:
        for key, value in merged.items():
            conn.execute(
                "INSERT INTO learning_settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
    return merged
