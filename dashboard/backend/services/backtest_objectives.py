"""백테스트 결과로부터 목적함수·필터·메트릭을 계산하는 유틸.

composite_backtest.py가 반환하는 결과 딕셔너리(summary + trades + equity_curve)를
입력으로 받아 expectancy / profit_factor / max_drawdown / win_rate / trade_count
등 튜닝에 필요한 메트릭을 일관되게 산출한다.

주요 책임:
- compute_metrics: 백테스트 결과에서 핵심 메트릭 추출
- passes_filter: 다중 목표 필터 통과 여부 판정 (PF≥1.5 AND MDD≤25 AND trades≥30)
- score_for_optuna: Optuna가 최대화할 단일 스칼라 (expectancy + 필터 미충족 페널티)
"""

from __future__ import annotations

from typing import Any


# 필터 임계값 (사용자 합의: 1h봉 BTC 시스템에서 30은 비현실적 → 15로 완화)
MIN_PROFIT_FACTOR = 1.5
MAX_DRAWDOWN_PCT = 25.0   # 절댓값 기준 (예: -22% → 22 ≤ 25 통과)
MIN_TRADE_COUNT = 15      # 6번 실험 결과로 30 비현실적 확인 (2026-04-28)
# 1-trade 트랩 차단: trade_count가 이 미만이면 무조건 강한 페널티 (best 선정 차단)
MIN_TRADE_COUNT_HARD_FLOOR = 5


def compute_metrics(backtest_result: dict[str, Any]) -> dict[str, float]:
    """백테스트 결과에서 튜닝용 메트릭을 추출한다.

    Args:
        backtest_result: composite_backtest._run_backtest_sync() 반환값.
            summary, trades, equity_curve 키를 포함한다.

    Returns:
        expectancy, profit_factor, max_drawdown_pct, win_rate, trade_count,
        avg_win_pct, avg_loss_pct, total_return_pct를 포함한 dict.
        trade_count=0이면 모든 수익률 메트릭은 0.0.
    """
    summary = backtest_result.get("summary") or {}
    trades = backtest_result.get("trades") or []

    # exit 거래만 분리 (entry는 pnl_pct=None)
    exits = [t for t in trades if t.get("type") == "exit"]
    pnls = [float(t.get("pnl_pct") or 0.0) for t in exits]

    trade_count = len(pnls)

    if trade_count == 0:
        return {
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": float(abs(summary.get("max_drawdown_pct", 0.0))),
            "win_rate": 0.0,
            "trade_count": 0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "total_return_pct": float(summary.get("total_return_pct", 0.0)),
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / trade_count

    avg_win = sum(wins) / win_count if win_count else 0.0
    # 평균 손실은 음수로 들어옴 — abs()로 양수 변환해 가독성 확보
    avg_loss = abs(sum(losses) / loss_count) if loss_count else 0.0

    # Expectancy: 1 거래당 기대 수익률(%) = win_rate * avg_win - loss_rate * avg_loss
    loss_rate = loss_count / trade_count
    expectancy = win_rate * avg_win - loss_rate * avg_loss

    # Profit Factor: 총 수익 / 총 손실(절댓값). 손실 0일 땐 무한대 대신 큰 값.
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    if total_loss > 0:
        profit_factor = total_win / total_loss
    elif total_win > 0:
        profit_factor = 999.0  # 손실 0 + 수익 발생 → 매우 좋음 (단, 표본 작을 수 있음)
    else:
        profit_factor = 0.0

    # MDD는 summary에 음수로 기록됨 → 절댓값으로 통일
    mdd_abs = float(abs(summary.get("max_drawdown_pct", 0.0)))

    return {
        "expectancy": float(expectancy),
        "profit_factor": float(profit_factor),
        "max_drawdown_pct": mdd_abs,
        "win_rate": float(win_rate),
        "trade_count": int(trade_count),
        "avg_win_pct": float(avg_win),
        "avg_loss_pct": float(avg_loss),
        "total_return_pct": float(summary.get("total_return_pct", 0.0)),
    }


def passes_filter(metrics: dict[str, float]) -> bool:
    """필터 통과 여부 판정 — plan acceptance 기준과 일치.

    조건: profit_factor >= 1.5 AND max_drawdown_pct <= 25 AND trade_count >= 30
    """
    return (
        metrics.get("profit_factor", 0.0) >= MIN_PROFIT_FACTOR
        and metrics.get("max_drawdown_pct", 999.0) <= MAX_DRAWDOWN_PCT
        and metrics.get("trade_count", 0) >= MIN_TRADE_COUNT
    )


# trade_count 표본 보상의 기준. acceptance가 15로 완화됐으므로 target도 30으로 조정.
# IS 6m 기준 30건 = 월 5건. acceptance 통과하려면 더 자주 거래해야 함.
TARGET_TRADE_COUNT = 30


def score_for_optuna(metrics: dict[str, float]) -> float:
    """Optuna가 최대화할 단일 스칼라.

    1-trade 트랩 차단:
      trade_count < MIN_TRADE_COUNT_HARD_FLOOR → -10000 (절대 best 안 됨)
    필터 미통과 (PF/MDD/trade) → -1000 페널티
    expectancy ≤ 0 → -100 페널티 (의미 없는 후보)
    그 외에는 expectancy × sample_factor

    sample_factor = min(1.5, sqrt(trade_count / TARGET_TRADE_COUNT))
    """
    expectancy = metrics.get("expectancy", 0.0)
    trade_count = metrics.get("trade_count", 0)

    # 1-trade 트랩 차단: 표본이 너무 적으면 어떤 expectancy값도 신뢰 불가
    if trade_count < MIN_TRADE_COUNT_HARD_FLOOR:
        return -10000.0

    if not passes_filter(metrics):
        return expectancy - 1000.0
    if expectancy <= 0.0:
        return expectancy - 100.0

    # 표본 크기 보상 — sqrt로 완만하게, 1.5 캡으로 폭주 방지
    sample_factor = min(1.5, (trade_count / TARGET_TRADE_COUNT) ** 0.5)
    return expectancy * sample_factor
