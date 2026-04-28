"""콘솔에서 walk-forward 자동 튜닝 실행. 결과는 backtest/results/tuning/{job_id}.json에 저장.

사용법:
    python scripts/run_tuning_smoke.py [--trials 200] [--windows 9]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

# PYTHONPATH 보강 (crypto-volatility-bot의 app 모듈 + 프로젝트 루트)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crypto-volatility-bot"))
sys.path.insert(0, str(ROOT))

# .env 로드 (FRED/CoinGecko/Bybit API key)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from dashboard.backend.services.composite_backtest import CompositeBacktestParams
from dashboard.backend.services.backtest_tuner import run_walk_forward, get_job_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--windows", type=int, default=9)
    parser.add_argument("--macro", type=float, default=55.0)
    parser.add_argument("--is-months", dest="is_months", type=int, default=3)
    parser.add_argument("--oos-months", dest="oos_months", type=int, default=1)
    parser.add_argument(
        "--no-derivatives", dest="use_derivatives", action="store_false",
        help="Phase 2 derivatives(OI+FR) 비활성. Phase 1만 격리 검증용."
    )
    parser.set_defaults(use_derivatives=True)
    parser.add_argument(
        "--phase1-indicators", dest="use_phase1_indicators", action="store_true",
        help="Phase 1 신규 5개 지표(OBV/MFI/VWAP/Volume Spike/Stoch RSI)를 search space에 포함."
    )
    parser.set_defaults(use_phase1_indicators=False)
    parser.add_argument(
        "--no-macro-timeseries", dest="use_macro_timeseries", action="store_false",
        help="Phase 3 macro 시계열(TGA+M2+Dominance) 비활성, 단일값 사용."
    )
    parser.set_defaults(use_macro_timeseries=True)
    args = parser.parse_args()

    base = CompositeBacktestParams(
        symbol=args.symbol,
        interval=args.interval,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
    )

    job_id = uuid.uuid4().hex[:12]
    out_path = get_job_path(job_id)

    print(f"[튜닝 시작] job_id={job_id}")
    print(f"  symbol={args.symbol} interval={args.interval}")
    print(f"  period={args.start} ~ {args.end}")
    print(f"  trials={args.trials} windows={args.windows} macro={args.macro} IS={args.is_months}m OOS={args.oos_months}m")
    print(f"  derivatives={args.use_derivatives} phase1_ind={args.use_phase1_indicators} macro_ts={args.use_macro_timeseries}")
    print(f"  결과 파일: {out_path}")
    print()

    t0 = time.time()
    result = run_walk_forward(
        job_id,
        base,
        n_trials=args.trials,
        n_windows=args.windows,
        macro_bullish=args.macro,
        is_start_months=args.is_months,
        oos_months=args.oos_months,
        use_derivatives=args.use_derivatives,
        use_phase1_indicators=args.use_phase1_indicators,
        use_macro_timeseries=args.use_macro_timeseries,
    )
    elapsed = time.time() - t0

    print()
    print(f"[완료] elapsed={elapsed:.1f}s status={result.get('status')}")
    agg = result.get("aggregate", {})
    if agg:
        print("=== aggregate ===")
        # top_combinations 제외하고 핵심 지표만 출력
        summary = {k: v for k, v in agg.items() if k != "top_combinations"}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print()
        top = agg.get("top_combinations", [])
        print(f"=== top {len(top)} combinations ===")
        for i, c in enumerate(top[:5]):
            m = c.get("metrics", {})
            p = c.get("params", {})
            print(
                f"  #{i+1} [w={c.get('window_index')}] "
                f"exp={m.get('expectancy', 0):.3f} "
                f"PF={m.get('profit_factor', 0):.2f} "
                f"WR={m.get('win_rate', 0)*100:.1f}% "
                f"MDD={m.get('max_drawdown_pct', 0):.2f}% "
                f"trades={m.get('trade_count')} "
                f"return={m.get('total_return_pct', 0):.2f}% | "
                f"L/S={p.get('long_threshold')}/{p.get('short_threshold')} "
                f"buf={p.get('score_exit_buffer')} "
                f"SL/TP={p.get('stop_loss_pct')}/{p.get('take_profit_pct')} "
                f"lev={p.get('leverage')}"
            )
    print()
    print(f"[저장됨] {out_path}")
    print(f"[UI에서 보려면] GET /api/sim/tune/{job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
