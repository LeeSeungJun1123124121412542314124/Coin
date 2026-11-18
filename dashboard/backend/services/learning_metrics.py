"""학습 탭 성과 지표 — 적중률·승률·DCA 기준선·계좌 자산 곡선."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services import learning_account


def hit_rate(horizon_days: int) -> dict:
    """국면 판정 적중률. 불명확(suggested NULL)·미확정 행은 제외, partial은 별도 비율."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT confirmed FROM learning_reviews WHERE horizon_days=? AND suggested IS NOT NULL"
            " AND confirmed IS NOT NULL", (horizon_days,)).fetchall()
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_rate": None, "partial_ratio": None}
    hit = sum(1 for r in rows if r["confirmed"] == "hit")
    partial = sum(1 for r in rows if r["confirmed"] == "partial")
    return {"n": n, "hit_rate": hit / n, "partial_ratio": partial / n}


def win_rate() -> dict:
    """청산 포지션 승률. 실현손익 = Σ매도(대금−수수료) − Σ매수 대금 > 0이면 승."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT p.id, COALESCE(SUM(CASE f.side WHEN 'sell' THEN f.usdt_amount - f.fee_usdt"
            " ELSE -f.usdt_amount END), 0) AS realized"
            " FROM learning_positions p JOIN learning_fills f ON f.position_id = p.id"
            " WHERE p.status='closed' GROUP BY p.id").fetchall()
    n = len(rows)
    if n == 0:
        return {"n": 0, "win_rate": None}
    return {"n": n, "win_rate": sum(1 for r in rows if r["realized"] > 0) / n}


def dca_baseline(start: date, until: date, closes: dict[date, float], initial: float = 10_000.0,
                 weeks: int = 52, fee: float = 0.001) -> list[dict]:
    """주간 정액 매수 기준선. 매수일 종가가 없으면 종가 있는 다음 날로 이월한다."""
    amount = initial / weeks
    buy_days = [start + timedelta(days=7 * k) for k in range(weeks)]
    buy_days = [d for d in buy_days if d <= until]
    days = sorted(d for d in closes if start <= d <= until)
    pending = {}  # 종가 있는 실제 체결일 → 매수 횟수
    for b in buy_days:
        day = next((d for d in days if d >= b), None)
        if day is not None:
            pending[day] = pending.get(day, 0) + 1
    cash, qty, out = initial, 0.0, []
    for d in days:
        for _ in range(pending.get(d, 0)):
            cash -= amount
            qty += amount * (1 - fee) / closes[d]
        out.append({"date": d.isoformat(), "value": cash + qty * closes[d]})
    return out


def account_equity_series(start: date, until: date) -> list[dict]:
    """날짜별 계좌 자산 = 그날까지 체결 반영 현금 + 종목별 보유수량 × 1d 종가(없으면 마지막 체결가)."""
    initial = learning_account.get_account()["initial_usdt"]
    with get_db() as conn:
        fills = [dict(r) for r in conn.execute(
            "SELECT symbol, side, qty, price, usdt_amount, fee_usdt, executed_at FROM learning_fills"
            " ORDER BY executed_at, id").fetchall()]
        symbols = {f["symbol"] for f in fills}
        closes = {s: {} for s in symbols}
        for s in symbols:
            for r in conn.execute(
                    "SELECT open_time, close FROM learning_candles WHERE symbol=? AND interval='1d'"
                    " ORDER BY open_time", (s,)).fetchall():
                closes[s][datetime.fromtimestamp(r["open_time"] / 1000, tz=timezone.utc).date()] = r["close"]
    for f in fills:
        f["day"] = datetime.fromisoformat(f["executed_at"]).astimezone(timezone.utc).date()
    out = []
    d = start
    while d <= until:
        cash, held, last_fill = initial, {}, {}
        for f in fills:
            if f["day"] > d:
                continue
            if f["side"] == "buy":
                cash -= f["usdt_amount"]
                held[f["symbol"]] = held.get(f["symbol"], 0.0) + f["qty"]
            else:
                cash += f["usdt_amount"] - f["fee_usdt"]
                held[f["symbol"]] = held.get(f["symbol"], 0.0) - f["qty"]
            last_fill[f["symbol"]] = f["price"]
        value = cash
        for s, q in held.items():
            if abs(q) < 1e-12:
                continue
            prior = [day for day in closes[s] if day <= d]
            price = closes[s][max(prior)] if prior else last_fill[s]
            value += q * price
        out.append({"date": d.isoformat(), "value": value})
        d += timedelta(days=1)
    return out
