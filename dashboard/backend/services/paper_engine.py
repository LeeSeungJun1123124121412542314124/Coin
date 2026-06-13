"""페이퍼 트레이딩 엔진 — 지표별 가상 포트폴리오의 신호→포지션·PnL·리밸런스.

순수 로직(app.macro 비의존). 신호(z)와 시세를 주입받아 동작하므로 단독 테스트 가능.
청산가만 sim_engine 재사용, PnL/수수료/펀딩은 자체 단순 수식.
스펙: docs/SPEC_paper-trading-leaderboard.md (#1·#3·#5)
"""

from __future__ import annotations

from datetime import datetime, timezone

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.sim_engine import calc_liquidation_price

# ── 상수 (config) ────────────────────────────────────────────
SEED = 10_000.0
N_ASSETS = 3
DEADBAND_Z = 0.2
Z_FULL = 1.0
LEV_CAP = 3.0
FEE_RATE = 0.0005      # 0.05% taker (composite_backtest 정합)
FUNDING_RATE = 0.0001  # 0.01%/일
BENCHMARK = "매수보유"
ASSETS = ["BTC", "ETH", "SOL"]


# ── 순수 함수 ────────────────────────────────────────────────
def compute_target(z: float, capital: float, indicator: str, leverage_cap: float = LEV_CAP) -> tuple[float, float]:
    """신호 z → (목표명목[부호=방향], 레버리지). 현금이면 (0, 0).

    - 매수보유: 항상 +1배 롱 (deadband·레버리지 무시, 벤치마크)
    - |z|<DEADBAND → 현금
    - 그 외: lev = min(|z|/Z_FULL, 1) × cap, 목표명목 = sign(z) × lev × (capital/N_ASSETS)
    """
    slot = capital / N_ASSETS
    if indicator == BENCHMARK:
        return slot, 1.0
    if abs(z) < DEADBAND_Z:
        return 0.0, 0.0
    lev = min(abs(z) / Z_FULL, 1.0) * leverage_cap
    return (1.0 if z > 0 else -1.0) * lev * slot, lev


def realized_pnl(direction: str, qty: float, entry: float, exit_price: float) -> float:
    """실현 손익 (롱=+, 숏 부호 반전)."""
    return (1 if direction == "long" else -1) * qty * (exit_price - entry)


def liquidation_hit(direction: str, liq_price: float | None, high: float, low: float) -> bool:
    """일봉 고저가가 청산가를 돌파했는지 (sim_engine 청산 규칙, 일봉판)."""
    if liq_price is None:
        return False
    return (direction == "long" and low <= liq_price) or (direction == "short" and high >= liq_price)


# ── 포트폴리오 관리 ──────────────────────────────────────────
def ensure_portfolios(indicators: list[str], seed: float = SEED, leverage_cap: float = LEV_CAP) -> None:
    """지표별 포트폴리오 없으면 시드로 생성."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        for ind in indicators:
            conn.execute(
                """INSERT OR IGNORE INTO paper_portfolios
                   (indicator, seed, capital, leverage_cap, created_at, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (ind, seed, seed, leverage_cap, now, now),
            )


def _open(conn, pid, asset, direction, qty, price, lev, at):
    liq = calc_liquidation_price(price, lev, direction)
    conn.execute(
        """INSERT INTO paper_positions
           (portfolio_id, asset, direction, qty, entry_price, leverage, liq_price, opened_at, status)
           VALUES (?,?,?,?,?,?,?,?, 'open')""",
        (pid, asset, direction, qty, price, lev, liq, at),
    )


def _close(conn, pos_id, exit_price, pnl, at):
    conn.execute(
        "UPDATE paper_positions SET status='closed', exit_price=?, pnl=?, closed_at=? WHERE id=?",
        (exit_price, pnl, at, pos_id),
    )


def rebalance(indicator: str, signals: dict[str, float], prices: dict[str, dict], at: str) -> dict:
    """하루치 리밸런스 — 청산판정 → 펀딩차감 → 목표 조정 → 에쿼티 스냅샷.

    signals: {asset: z}, prices: {asset: {'close','high','low'}}, at: ISO 시각.
    반환: {'equity', 'capital', 'trades'}.
    """
    date = at[:10]
    with get_db() as conn:
        pf = conn.execute(
            "SELECT id, capital, leverage_cap FROM paper_portfolios WHERE indicator=?", (indicator,)
        ).fetchone()
        if pf is None:
            raise ValueError(f"포트폴리오 없음: {indicator}")
        pid, capital, lev_cap = pf["id"], pf["capital"], pf["leverage_cap"]
        base_capital = capital  # 사이징 기준(자산 순회 중 불변)
        trades: list[str] = []

        for asset, px in prices.items():
            close, high, low = px["close"], px["high"], px["low"]
            pos = conn.execute(
                "SELECT * FROM paper_positions WHERE portfolio_id=? AND asset=? AND status='open'",
                (pid, asset),
            ).fetchone()

            # 1) 기존 포지션 청산 판정
            if pos and liquidation_hit(pos["direction"], pos["liq_price"], high, low):
                liq = pos["liq_price"]
                pnl = realized_pnl(pos["direction"], pos["qty"], pos["entry_price"], liq)
                capital += pnl - FEE_RATE * pos["qty"] * liq
                _close(conn, pos["id"], liq, pnl, at)
                trades.append(f"{asset}:liquidated")
                pos = None

            # 2) 생존 포지션 펀딩 차감
            if pos:
                capital -= FUNDING_RATE * pos["qty"] * close

            # 3) 목표 포지션
            notional, lev = compute_target(signals.get(asset, 0.0), base_capital, indicator, lev_cap)
            tdir = "long" if notional > 0 else "short" if notional < 0 else None
            tqty = abs(notional) / close if tdir else 0.0

            # 4) 정산
            if pos is None:
                if tdir:
                    _open(conn, pid, asset, tdir, tqty, close, lev, at)
                    capital -= FEE_RATE * tqty * close
                    trades.append(f"{asset}:open:{tdir}")
            elif tdir is None:  # 청산(flat)
                pnl = realized_pnl(pos["direction"], pos["qty"], pos["entry_price"], close)
                capital += pnl - FEE_RATE * pos["qty"] * close
                _close(conn, pos["id"], close, pnl, at)
                trades.append(f"{asset}:flat")
            elif tdir != pos["direction"]:  # flip → 청산 후 반대 진입
                pnl = realized_pnl(pos["direction"], pos["qty"], pos["entry_price"], close)
                capital += pnl - FEE_RATE * pos["qty"] * close
                _close(conn, pos["id"], close, pnl, at)
                _open(conn, pid, asset, tdir, tqty, close, lev, at)
                capital -= FEE_RATE * tqty * close
                trades.append(f"{asset}:flip:{tdir}")
            else:  # 동일 방향 → 델타만 매매 (VWAP)
                dq = tqty - pos["qty"]
                if abs(dq) * close > 1e-9:
                    capital -= FEE_RATE * abs(dq) * close
                    if dq > 0:  # 증가 → 진입가 가중평균
                        entry = (pos["qty"] * pos["entry_price"] + dq * close) / tqty
                    else:       # 감소 → 부분 실현
                        capital += realized_pnl(pos["direction"], -dq, pos["entry_price"], close)
                        entry = pos["entry_price"]
                    liq = calc_liquidation_price(entry, lev, tdir)
                    conn.execute(
                        "UPDATE paper_positions SET qty=?, entry_price=?, leverage=?, liq_price=? WHERE id=?",
                        (tqty, entry, lev, liq, pos["id"]),
                    )
                    trades.append(f"{asset}:adjust")

        # 5) 에쿼티 = 현금 + 미실현
        opens = conn.execute(
            "SELECT asset, direction, qty, entry_price FROM paper_positions WHERE portfolio_id=? AND status='open'",
            (pid,),
        ).fetchall()
        unreal = sum(
            realized_pnl(o["direction"], o["qty"], o["entry_price"], prices[o["asset"]]["close"])
            for o in opens if o["asset"] in prices
        )
        equity = capital + unreal

        prev = conn.execute(
            "SELECT equity FROM paper_equity WHERE portfolio_id=? AND date<? ORDER BY date DESC LIMIT 1",
            (pid, date),
        ).fetchone()
        ret_pct = (equity / prev["equity"] - 1) * 100 if prev else (equity / SEED - 1) * 100

        conn.execute(
            "UPDATE paper_portfolios SET capital=?, updated_at=? WHERE id=?", (capital, at, pid)
        )
        conn.execute(
            """INSERT INTO paper_equity (portfolio_id, date, equity, return_pct) VALUES (?,?,?,?)
               ON CONFLICT(portfolio_id, date) DO UPDATE SET equity=excluded.equity, return_pct=excluded.return_pct""",
            (pid, date, equity, ret_pct),
        )

    return {"equity": equity, "capital": capital, "trades": trades}


# ── 집계 (리더보드) ──────────────────────────────────────────
def _curve_stats(equities: list[float], daily_returns: list[float], seed: float) -> dict:
    """에쿼티 곡선 → 총수익·MDD·Sharpe."""
    if not equities:
        return {"total_return_pct": 0.0, "mdd_pct": 0.0, "sharpe": 0.0, "equity": seed}
    last = equities[-1]
    peak, mdd = equities[0], 0.0
    for e in equities:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    sharpe = 0.0
    if len(daily_returns) > 1:
        m = sum(daily_returns) / len(daily_returns)
        var = sum((x - m) ** 2 for x in daily_returns) / (len(daily_returns) - 1)
        sd = var ** 0.5
        if sd > 0:
            sharpe = m / sd * (252 ** 0.5)  # 일별→연율화
    return {
        "total_return_pct": (last / seed - 1) * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "equity": last,
    }


def leaderboard() -> list[dict]:
    """지표별 총수익·승률·MDD·Sharpe·vs매수보유, 총수익 내림차순."""
    with get_db() as conn:
        pfs = conn.execute("SELECT * FROM paper_portfolios").fetchall()
        out = []
        for pf in pfs:
            eq = conn.execute(
                "SELECT equity, return_pct FROM paper_equity WHERE portfolio_id=? ORDER BY date",
                (pf["id"],),
            ).fetchall()
            closed = conn.execute(
                "SELECT pnl FROM paper_positions WHERE portfolio_id=? AND status='closed'", (pf["id"],)
            ).fetchall()
            wins = sum(1 for c in closed if c["pnl"] and c["pnl"] > 0)
            n = len(closed)
            st = _curve_stats(
                [r["equity"] for r in eq],
                [r["return_pct"] / 100 for r in eq if r["return_pct"] is not None],
                pf["seed"],
            )
            st.update(
                indicator=pf["indicator"], seed=pf["seed"], capital=pf["capital"],
                win_rate=(wins / n * 100 if n else None), n_trades=n,
            )
            out.append(st)
    bh = next((r["total_return_pct"] for r in out if r["indicator"] == BENCHMARK), None)
    for r in out:
        r["vs_buyhold_pct"] = (r["total_return_pct"] - bh) if bh is not None else None
    out.sort(key=lambda r: r["total_return_pct"], reverse=True)
    return out


def portfolio_detail(indicator: str) -> dict | None:
    """특정 지표의 에쿼티 곡선 + 포지션 이력."""
    with get_db() as conn:
        pf = conn.execute("SELECT * FROM paper_portfolios WHERE indicator=?", (indicator,)).fetchone()
        if pf is None:
            return None
        eq = conn.execute(
            "SELECT date, equity, return_pct FROM paper_equity WHERE portfolio_id=? ORDER BY date",
            (pf["id"],),
        ).fetchall()
        pos = conn.execute(
            "SELECT asset, direction, qty, entry_price, leverage, liq_price, opened_at, closed_at, exit_price, pnl, status "
            "FROM paper_positions WHERE portfolio_id=? ORDER BY opened_at DESC, id DESC",
            (pf["id"],),
        ).fetchall()
    return {
        "indicator": pf["indicator"], "seed": pf["seed"], "capital": pf["capital"],
        "equity_curve": [dict(r) for r in eq],
        "positions": [dict(p) for p in pos],
    }


def reset(indicator: str | None = None, seed: float = SEED) -> int:
    """시드 리셋 — 포지션·에쿼티 삭제 + 자본 복원. indicator=None이면 전체. 리셋 수 반환."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        if indicator:
            row = conn.execute("SELECT id FROM paper_portfolios WHERE indicator=?", (indicator,)).fetchone()
            ids = [row["id"]] if row else []
        else:
            ids = [r["id"] for r in conn.execute("SELECT id FROM paper_portfolios").fetchall()]
        for pid in ids:
            conn.execute("DELETE FROM paper_positions WHERE portfolio_id=?", (pid,))
            conn.execute("DELETE FROM paper_equity WHERE portfolio_id=?", (pid,))
            conn.execute(
                "UPDATE paper_portfolios SET seed=?, capital=?, updated_at=? WHERE id=?",
                (seed, seed, now, pid),
            )
    return len(ids)
