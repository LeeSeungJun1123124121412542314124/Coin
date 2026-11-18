"""학습 탭 일지·포지션 복기·국면 자동 판정 — 첫 진입 14·28일 뒤 종가 기준."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_settings import LearningError

HORIZONS = (14, 28)
JUDGE_PCT = 5.0
_VERDICTS = ("hit", "partial", "miss")
_REASON_MAX = 1000
_UP_PHASES = ("accumulation", "markup")
_DOWN_PHASES = ("distribution", "markdown")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def judge_phase(phase: str, entry_price: float, close_price: float, pct: float = JUDGE_PCT) -> str | None:
    """진입 국면 대비 사후 수익률로 hit/partial/miss 판정. 상승 국면은 +pct 이상 hit, 하락 국면은 부호 반대."""
    if phase not in _UP_PHASES + _DOWN_PHASES:
        return None
    ret = round((close_price / entry_price - 1) * 100, 9)
    if phase in _DOWN_PHASES:
        ret = -ret
    if ret >= pct:
        return "hit"
    if ret <= -pct:
        return "miss"
    return "partial"


def _utc_date(iso: str) -> date:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _loads(s: str | None):
    return json.loads(s) if s is not None else None


def _fill_dict(row) -> dict:
    d = dict(row)
    d["ichimoku"] = _loads(d.pop("ichimoku_json"))
    d["detected"] = _loads(d.pop("detected_json"))
    d["snapshot"] = _loads(d.pop("snapshot_json"))
    return d


def position_exists(position_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM learning_positions WHERE id=?", (position_id,)).fetchone() is not None


def journal(limit: int = 50) -> list[dict]:
    """포지션별(최근 진입순) 체결 목록 — 근거·스냅샷 JSON은 파싱해서 반환."""
    with get_db() as conn:
        positions = conn.execute(
            "SELECT * FROM learning_positions ORDER BY opened_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [{
            "position": dict(p),
            "fills": [_fill_dict(f) for f in conn.execute(
                "SELECT * FROM learning_fills WHERE position_id=? ORDER BY executed_at, id", (p["id"],)).fetchall()],
        } for p in positions]


def _review_row(conn, position_id: int, horizon_days: int) -> dict | None:
    row = conn.execute(
        "SELECT suggested, confirmed, reason, close_price FROM learning_reviews"
        " WHERE position_id=? AND horizon_days=?", (position_id, horizon_days)).fetchone()
    return dict(row) if row else None


def review_position(position_id: int, horizon_days: int, today: date | None = None) -> dict:
    """첫 진입 + horizon일의 1d 종가 기준 복기. 기준일 미도래·캔들 없음이면 pending(저장 안 함)."""
    if horizon_days not in HORIZONS:
        raise LearningError(f"복기 기간은 {HORIZONS}일 중 하나여야 합니다")
    today = today or datetime.now(timezone.utc).date()
    with get_db() as conn:
        pos = conn.execute("SELECT * FROM learning_positions WHERE id=?", (position_id,)).fetchone()
        if pos is None:
            raise LearningError(f"포지션을 찾을 수 없습니다: {position_id}")
        due = _utc_date(pos["opened_at"]) + timedelta(days=horizon_days)
        pending = {"status": "pending", "due": due.isoformat()}
        if due > today:
            return pending
        open_ms = int(datetime(due.year, due.month, due.day, tzinfo=timezone.utc).timestamp() * 1000)
        candle = conn.execute(
            "SELECT close FROM learning_candles WHERE symbol=? AND interval='1d' AND open_time=?",
            (pos["symbol"], open_ms)).fetchone()
        if candle is None or candle["close"] is None:
            return pending
        close = candle["close"]
        fills = conn.execute(
            "SELECT * FROM learning_fills WHERE position_id=? ORDER BY executed_at, id", (position_id,)).fetchall()
        # 기준일(UTC) 이하 체결만 반영: 실현(매도 순수령) + 잔량 평가 - 매수 총액
        in_range = [f for f in fills if _utc_date(f["executed_at"]) <= due]
        buys = [f for f in in_range if f["side"] == "buy"]
        sells = [f for f in in_range if f["side"] == "sell"]
        remaining = sum(f["qty"] for f in buys) - sum(f["qty"] for f in sells)
        pnl = (sum(f["usdt_amount"] - f["fee_usdt"] for f in sells) + remaining * close
               - sum(f["usdt_amount"] for f in buys))
        suggested = judge_phase(pos["entry_phase"], pos["first_entry_price"], close)
        # confirmed·reason은 건드리지 않는다 (재복기해도 사용자 확정값 보존)
        conn.execute(
            "INSERT INTO learning_reviews(position_id, horizon_days, suggested, close_price, judged_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT(position_id, horizon_days) DO UPDATE SET"
            " suggested=excluded.suggested, close_price=excluded.close_price, judged_at=excluded.judged_at",
            (position_id, horizon_days, suggested, close, _now()))
        saved = _review_row(conn, position_id, horizon_days)
        first = _fill_dict(fills[0])
    return {
        "status": "ready",
        "rationale": {"phase": first["phase"], "ichimoku": first["ichimoku"],
                      "detected": first["detected"], "memo": first["memo"]},
        "close_price": close,
        "pnl_usdt": pnl,
        "hold_return_pct": (close / pos["first_entry_price"] - 1) * 100,
        "suggested": saved["suggested"], "confirmed": saved["confirmed"], "reason": saved["reason"],
    }


def confirm_review(position_id: int, horizon_days: int, verdict: str, reason: str) -> dict:
    """사용자가 제안 판정을 확정/뒤집는다. 사유 필수. 적중률(Task 12)은 이 행만 집계."""
    if horizon_days not in HORIZONS:
        raise LearningError(f"복기 기간은 {HORIZONS}일 중 하나여야 합니다")
    if verdict not in _VERDICTS:
        raise LearningError(f"판정은 {_VERDICTS} 중 하나여야 합니다")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= _REASON_MAX:
        raise LearningError(f"사유는 1~{_REASON_MAX}자여야 합니다")
    reason = reason.strip()
    with get_db() as conn:
        row = _review_row(conn, position_id, horizon_days)
        if row is None:
            raise LearningError("아직 복기할 수 없습니다 (기준일 미도래 또는 종가 없음)")
        if row["suggested"] is None:
            raise LearningError("국면이 불명확한 포지션은 판정하지 않습니다")
        conn.execute("UPDATE learning_reviews SET confirmed=?, reason=? WHERE position_id=? AND horizon_days=?",
                     (verdict, reason, position_id, horizon_days))
        return _review_row(conn, position_id, horizon_days)
