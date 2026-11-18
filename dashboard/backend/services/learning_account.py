"""학습 탭 모의 계좌·현물 주문 — 가상 10,000 USDT, 수수료 0.1%, 근거 필수."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_settings import LearningError

INITIAL_USDT = 10_000.0
FEE_RATE = 0.001
QTY_EPS = 1e-9
PHASES = {"accumulation", "markup", "distribution", "markdown", "unclear"}
_ICHIMOKU_ALLOWED = {
    "cloud_position": {"above", "inside", "below"},
    "tk_cross": {"golden", "dead", "none"},
    "chikou": {"above", "below"},
    "future_cloud": {"bullish", "bearish"},
}
_MEMO_MAX = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_rationale(r: dict) -> dict:
    """근거 검증 후 정규화해 반환. 위반 시 LearningError. 일목 값 None은 '판단 불가'로 허용."""
    if not isinstance(r, dict):
        raise LearningError("근거(rationale)가 필요합니다")
    phase = r.get("phase")
    if phase not in PHASES:
        raise LearningError(f"와이코프 국면이 필요합니다: {sorted(PHASES)}")
    ich = r.get("ichimoku")
    if not isinstance(ich, dict) or set(_ICHIMOKU_ALLOWED) - set(ich):
        raise LearningError(f"일목 상태 4개 항목이 모두 필요합니다: {sorted(_ICHIMOKU_ALLOWED)}")
    norm_ich = {}
    for key, allowed in _ICHIMOKU_ALLOWED.items():
        v = ich[key]
        if v is not None and v not in allowed:
            raise LearningError(f"일목 {key} 값이 올바르지 않습니다: {v}")
        norm_ich[key] = v
    out = {"phase": phase, "ichimoku": norm_ich}
    memo = r.get("memo")
    if memo is not None:
        if not isinstance(memo, str) or len(memo) > _MEMO_MAX:
            raise LearningError(f"메모는 {_MEMO_MAX}자 이하 문자열이어야 합니다")
        out["memo"] = memo
    return out


def _account_row(conn) -> dict:
    """계좌 행을 읽고, 없으면 초기값으로 생성한다 (호출자의 트랜잭션 안에서)."""
    row = conn.execute("SELECT started_at, initial_usdt, cash_usdt FROM learning_account WHERE id=1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO learning_account(id, started_at, initial_usdt, cash_usdt) VALUES (1,?,?,?)",
            (_now(), INITIAL_USDT, INITIAL_USDT),
        )
        row = conn.execute("SELECT started_at, initial_usdt, cash_usdt FROM learning_account WHERE id=1").fetchone()
    return dict(row)


def get_account() -> dict:
    with get_db() as conn:
        return _account_row(conn)


def _held_qty(conn, position_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE side WHEN 'buy' THEN qty ELSE -qty END), 0) AS q"
        " FROM learning_fills WHERE position_id=?", (position_id,),
    ).fetchone()
    return row["q"]


def open_positions() -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM learning_positions WHERE status='open' ORDER BY id").fetchall()]


def place_order(symbol: str, side: str, price: float, rationale: dict, snapshot: dict, *,
                usdt_amount: float | None = None, qty: float | None = None,
                detected: dict | None = None, executed_at: str | None = None) -> dict:
    if side not in ("buy", "sell"):
        raise LearningError(f"주문 방향이 올바르지 않습니다: {side}")
    if not price or price <= 0:
        raise LearningError("체결가가 올바르지 않습니다")
    r = validate_rationale(rationale)
    executed_at = executed_at or _now()
    with get_db() as conn:
        cash = _account_row(conn)["cash_usdt"]
        pos = conn.execute(
            "SELECT id FROM learning_positions WHERE symbol=? AND status='open'", (symbol,)).fetchone()
        if side == "buy":
            if usdt_amount is None or usdt_amount <= 0:
                raise LearningError("매수 금액(usdt_amount)은 0보다 커야 합니다")
            if usdt_amount > cash + 1e-9:
                raise LearningError("보유 현금이 부족합니다")
            fee = usdt_amount * FEE_RATE
            fill_qty = (usdt_amount - fee) / price
            fill_amount = usdt_amount
            new_cash = cash - usdt_amount
            if pos is None:
                cur = conn.execute(
                    "INSERT INTO learning_positions(symbol, opened_at, entry_phase, first_entry_price, status)"
                    " VALUES (?,?,?,?, 'open')", (symbol, executed_at, r["phase"], price))
                position_id = cur.lastrowid
            else:
                position_id = pos["id"]
            close = False
        else:
            if pos is None:
                raise LearningError("열린 포지션이 없어 매도할 수 없습니다")
            position_id = pos["id"]
            held = _held_qty(conn, position_id)
            if qty is None or qty <= 0:
                raise LearningError("매도 수량(qty)은 0보다 커야 합니다")
            if qty > held + QTY_EPS:
                raise LearningError("보유 수량을 초과할 수 없습니다")
            fill_qty = qty
            fill_amount = qty * price
            fee = fill_amount * FEE_RATE
            new_cash = cash + fill_amount - fee
            close = held - qty < QTY_EPS
        cur = conn.execute(
            "INSERT INTO learning_fills(position_id, symbol, side, qty, price, usdt_amount, fee_usdt, executed_at,"
            " phase, ichimoku_json, detected_json, memo, snapshot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (position_id, symbol, side, fill_qty, price, fill_amount, fee, executed_at, r["phase"],
             json.dumps(r["ichimoku"]), json.dumps(detected) if detected is not None else None,
             r.get("memo"), json.dumps(snapshot)))
        fill_id = cur.lastrowid
        conn.execute("UPDATE learning_account SET cash_usdt=? WHERE id=1", (new_cash,))
        if close:
            conn.execute("UPDATE learning_positions SET status='closed', closed_at=? WHERE id=?",
                         (executed_at, position_id))
    return {"fill_id": fill_id, "position_id": position_id, "qty": fill_qty, "price": price,
            "fee_usdt": fee, "cash_usdt": new_cash}


def holdings(prices: dict[str, float], usd_krw: float | None) -> dict:
    """열린 포지션 평가. 시세 없는 종목이 있으면 equity는 None."""
    account = get_account()
    positions = []
    with get_db() as conn:
        for p in conn.execute("SELECT id, symbol FROM learning_positions WHERE status='open' ORDER BY id").fetchall():
            row = conn.execute(
                "SELECT COALESCE(SUM(CASE side WHEN 'buy' THEN qty ELSE -qty END), 0) AS q,"
                " COALESCE(SUM(CASE side WHEN 'buy' THEN usdt_amount ELSE 0 END), 0) AS cost,"
                " COALESCE(SUM(CASE side WHEN 'buy' THEN qty ELSE 0 END), 0) AS bq"
                " FROM learning_fills WHERE position_id=?", (p["id"],)).fetchone()
            qty, avg_cost = row["q"], row["cost"] / row["bq"]
            price = prices.get(p["symbol"])
            positions.append({
                "symbol": p["symbol"], "qty": qty, "avg_cost": avg_cost,
                "market_value": qty * price if price is not None else None,
                "unrealized_pnl": qty * (price - avg_cost) if price is not None else None,
            })
    cash = account["cash_usdt"]
    if any(p["market_value"] is None for p in positions):
        equity = None
    else:
        equity = cash + sum(p["market_value"] for p in positions)
    return {"cash_usdt": cash, "positions": positions, "equity_usdt": equity,
            "equity_krw": equity * usd_krw if equity is not None and usd_krw is not None else None}
