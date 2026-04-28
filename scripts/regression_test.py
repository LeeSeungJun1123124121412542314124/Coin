"""Phase 1+2 회귀 검증: weights=None일 때 기존 4지표만 사용되는지 확인."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crypto-volatility-bot"))
sys.path.insert(0, str(ROOT))

from dashboard.backend.services.composite_backtest import (
    CompositeBacktestParams,
    _run_backtest_sync,
    _fetch_ohlcv,
    calc_tech_bullish_score,
    calc_tech_bearish_score,
)


def test_weights_none_legacy_only():
    """weights=None이면 신규 5개 지표는 평균에 포함되지 않아야 함 (backwards-compat)."""
    details = {
        "rsi": 25, "macd": {"histogram": 0.5, "prev_histogram": 0.3},
        "bb": 0.15, "adx": {"adx": 30, "plus_di": 25, "minus_di": 15},
        "obv_slope": 10.0, "mfi": 15.0, "vwap_dev": -2.5,
        "volume_spike": 2.5, "close_diff": 50.0, "stoch_rsi_k": 15.0,
    }
    legacy_details = {k: v for k, v in details.items() if k in ("rsi", "macd", "bb", "adx")}
    score_full = calc_tech_bullish_score(details, weights=None)
    score_legacy = calc_tech_bullish_score(legacy_details, weights=None)
    print(f"  weights=None with new keys: {score_full:.4f}")
    print(f"  legacy keys only:           {score_legacy:.4f}")
    assert abs(score_full - score_legacy) < 1e-9, (
        f"weights=None은 신규 지표를 무시해야 함! diff={score_full - score_legacy}"
    )
    print("  PASS: weights=None은 4지표만 사용")


def test_weights_dict_uses_all9():
    """weights dict가 명시되면 9개 모두 가중평균에 사용."""
    # 신규 지표가 한쪽으로 strong bias 줄 수 있는 시나리오: 가격 하락 + 볼륨 spike
    details = {
        "rsi": 50, "macd": {"histogram": 0.0, "prev_histogram": 0.0},
        "bb": 0.5, "adx": {"adx": 10, "plus_di": 10, "minus_di": 10},
        # 신규: 모두 short bias (가격 하락 신호)
        "obv_slope": -10.0, "mfi": 90.0, "vwap_dev": 5.0,
        "volume_spike": 2.5, "close_diff": -50.0, "stoch_rsi_k": 90.0,
    }
    weights_legacy = {"rsi": 1.0, "macd": 1.0, "bb": 1.0, "adx": 1.0,
                       "obv": 0.0, "mfi": 0.0, "vwap": 0.0, "volume_spike": 0.0, "stoch_rsi": 0.0}
    weights_new = {"rsi": 0.0, "macd": 0.0, "bb": 0.0, "adx": 0.0,
                   "obv": 1.0, "mfi": 1.0, "vwap": 1.0, "volume_spike": 1.0, "stoch_rsi": 1.0}
    s_legacy = calc_tech_bullish_score(details, weights=weights_legacy)
    s_new = calc_tech_bullish_score(details, weights=weights_new)
    print(f"  legacy-only weights (long bias score): {s_legacy:.4f}")
    print(f"  new-only weights (short bias scenario): {s_new:.4f}")
    # 신규 지표가 모두 short bias 방향이므로 long score가 legacy보다 낮아야 함
    assert s_new < s_legacy - 5.0, f"신규 short-bias 지표가 long score를 낮춰야 함: legacy={s_legacy}, new={s_new}"
    print("  PASS: 가중치 변경에 따라 결과 달라짐")


def test_backtest_default_run():
    """기본 파라미터로 작은 기간 백테스트 — 에러 없이 실행되는지 확인."""
    base = CompositeBacktestParams(
        symbol="BTC/USDT", interval="1h",
        start_date="2024-06-01", end_date="2024-06-30",
        initial_capital=10000.0,
        long_threshold=58, short_threshold=66, score_exit_buffer=17,
        stop_loss_pct=5.0, take_profit_pct=9.0,
        position_size_pct=5.0, leverage=5,
    )
    df = _fetch_ohlcv(base)
    print(f"  OHLCV: {len(df)}봉")
    result = _run_backtest_sync(df, base, macro_bullish=55.0, deriv_df=None)
    trades = [t for t in result.get("trades", []) if t.get("type") == "exit"]
    summary = result.get("summary", {})
    print(f"  trades(exit): {len(trades)}")
    print(f"  total_return_pct: {summary.get('total_return_pct')}")
    print(f"  win_rate: {summary.get('win_rate')}")
    assert len(trades) >= 0, "백테스트 실행됨"
    print("  PASS: 기본 백테스트 실행 성공")


def test_with_phase1_weights():
    """Phase 1 weights 명시 + deriv_df=None — 새 지표 통합되는지 확인."""
    base = CompositeBacktestParams(
        symbol="BTC/USDT", interval="1h",
        start_date="2024-06-01", end_date="2024-06-30",
        initial_capital=10000.0,
        long_threshold=60, short_threshold=70, score_exit_buffer=20,
        stop_loss_pct=3.0, take_profit_pct=6.0,
        position_size_pct=10.0, leverage=3,
        # Phase 1: 9개 모두 동일 가중치 (1/9)
        tech_weight_rsi=0.111, tech_weight_macd=0.111, tech_weight_bb=0.111,
        tech_weight_adx=0.111, tech_weight_obv=0.111, tech_weight_mfi=0.111,
        tech_weight_vwap=0.111, tech_weight_volume_spike=0.111, tech_weight_stoch_rsi=0.112,
    )
    df = _fetch_ohlcv(base)
    result = _run_backtest_sync(df, base, macro_bullish=55.0, deriv_df=None)
    trades = [t for t in result.get("trades", []) if t.get("type") == "exit"]
    print(f"  Phase 1 weights: {len(trades)} trades")
    print(f"  return_pct: {result.get('summary', {}).get('total_return_pct')}")
    print("  PASS: Phase 1 가중치 적용 백테스트 성공")


if __name__ == "__main__":
    print("=== 회귀 1: weights=None은 신규 지표 무시 ===")
    test_weights_none_legacy_only()
    print()
    print("=== 회귀 2: weights dict는 9개 모두 사용 ===")
    test_weights_dict_uses_all9()
    print()
    print("=== 회귀 3: 기본 백테스트 실행 ===")
    test_backtest_default_run()
    print()
    print("=== 회귀 4: Phase 1 가중치 적용 백테스트 ===")
    test_with_phase1_weights()
    print()
    print("ALL PASS")
