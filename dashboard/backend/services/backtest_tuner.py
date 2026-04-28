"""백테스트 자동 튜닝 + Walk-Forward 검증.

composite_backtest._run_backtest_sync()를 재사용하여 Optuna TPE 베이지안 최적화로
12개 파라미터를 탐색하고, Expanding Window walk-forward로 과적합을 방지한다.

핵심 흐름:
1. 전체 OHLCV 데이터 1회 fetch (re-fetch 방지)
2. Expanding window 9개 정의: IS 3→11개월, OOS 1개월씩
3. 각 window에서 Optuna study 1개 실행:
   - IS 기간 백테스트로 score_for_optuna 최대화
   - best params를 OOS 기간에 적용해 OOS 메트릭 산출
4. 9 windows OOS 평균 + 필터 통과 여부 판정
5. JSON 결과 파일 저장 (실시간 진행률 갱신)

설계 원칙:
- composite_backtest.py의 _run_backtest_sync() 핵심 로직은 호출만, 수정하지 않음.
- 가중치는 CompositeBacktestParams 필드(default=None)로 backwards-compat 보장.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import optuna
import pandas as pd

from dashboard.backend.services.backtest_objectives import (
    compute_metrics,
    passes_filter,
    score_for_optuna,
)
from dashboard.backend.services.composite_backtest import (
    CompositeBacktestParams,
    _fetch_ohlcv,
    _run_backtest_sync,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 결과 저장 경로
# ---------------------------------------------------------------------------

# 프로젝트 루트의 backtest/results/tuning/{job_id}.json
_RESULTS_DIR = Path(__file__).resolve().parents[3] / "backtest" / "results" / "tuning"


def get_results_dir() -> Path:
    """튜닝 결과 저장 디렉토리. 없으면 생성."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return _RESULTS_DIR


def get_job_path(job_id: str) -> Path:
    """job_id에 해당하는 결과 파일 경로."""
    return get_results_dir() / f"{job_id}.json"


# ---------------------------------------------------------------------------
# Expanding Window 정의 (plan: IS 3→11개월, OOS 1개월, 9 windows)
# ---------------------------------------------------------------------------

def make_expanding_windows(
    full_df: pd.DataFrame,
    n_windows: int = 9,
    is_start_months: int = 3,
    oos_months: int = 1,
) -> list[dict[str, str]]:
    """전체 DataFrame을 expanding window로 분할.

    각 window: IS는 데이터 시작부터 (is_start_months + i)개월,
               OOS는 IS 종료 다음부터 oos_months개월.

    Args:
        full_df: datetime 인덱스를 가진 OHLCV DataFrame (UTC).
        n_windows: 생성할 window 수 (기본 9).
        is_start_months: 첫 window의 IS 기간 (개월 수).
        oos_months: 각 OOS 기간 (개월 수).

    Returns:
        각 window별 {is_start, is_end, oos_start, oos_end} ISO8601 문자열 dict 리스트.
        데이터가 부족해서 만들 수 없는 window는 건너뜀.
    """
    if full_df.empty:
        return []

    t0 = full_df.index[0]
    t_last = full_df.index[-1]

    windows: list[dict[str, str]] = []
    for i in range(n_windows):
        is_end = t0 + pd.DateOffset(months=is_start_months + i)
        oos_start = is_end
        oos_end = oos_start + pd.DateOffset(months=oos_months)

        if oos_end > t_last + pd.Timedelta(days=1):
            # 데이터 끝을 넘어가면 가능한 만큼만 자름
            if oos_start >= t_last:
                break
            oos_end = t_last

        windows.append({
            "is_start": t0.isoformat(),
            "is_end": is_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
        })

    return windows


# ---------------------------------------------------------------------------
# Optuna search space (12 파라미터 — plan과 일치)
# ---------------------------------------------------------------------------

def define_search_space(
    trial: optuna.Trial,
    base_params: CompositeBacktestParams,
    use_derivatives: bool = True,
    use_phase1_indicators: bool = False,
) -> CompositeBacktestParams:
    """Optuna trial 객체로부터 파라미터를 샘플링하여 CompositeBacktestParams 생성.

    파라미터 구성:
      - 임계값/SL/TP/포지션: 5개 (long/short/score_exit_buffer/SL/TP)
      - 사이즈/레버리지: 2개 (position_size, leverage)
      - 매크로 비율: 1개 (macro_weight)
      - 기술 가중치: 4개 기본 (rsi/macd/bb/adx)
        + use_phase1_indicators=True일 때만 5개 추가 (obv/mfi/vwap/volume_spike/stoch_rsi)
      - 파생: 0 또는 1개 (use_derivatives에 따라)
    base_params는 symbol/interval/initial_capital 등 튜닝 대상이 아닌 필드의 원본 값.

    use_phase1_indicators=False(기본): 5번 실험에서 신규 5개 지표가 noise로 확인되어
    search space에서 제외 — 4지표 기본 + macro + derivatives 조합으로 베이스라인 유지.
    """
    long_threshold = trial.suggest_int("long_threshold", 50, 85)
    short_threshold = trial.suggest_int("short_threshold", 50, 85)
    # score_exit_buffer는 두 threshold보다 모두 작아야 함
    upper = min(long_threshold, short_threshold) - 1
    if upper < 5:
        upper = 5
    score_exit_buffer = trial.suggest_int("score_exit_buffer", 5, max(5, upper))

    stop_loss_pct = trial.suggest_float("stop_loss_pct", 1.0, 5.0, step=0.5)
    take_profit_pct = trial.suggest_float("take_profit_pct", 2.0, 10.0, step=0.5)
    position_size_pct = trial.suggest_float("position_size_pct", 5.0, 30.0, step=5.0)
    leverage = trial.suggest_int("leverage", 1, 5)

    macro_weight = trial.suggest_float("macro_weight", 0.2, 0.6, step=0.05)

    # 기술 가중치 raw 샘플링 → 합 1로 정규화
    w_rsi_raw = trial.suggest_float("weight_rsi", 0.05, 1.0)
    w_macd_raw = trial.suggest_float("weight_macd", 0.05, 1.0)
    w_bb_raw = trial.suggest_float("weight_bb", 0.05, 1.0)
    w_adx_raw = trial.suggest_float("weight_adx", 0.05, 1.0)

    # Phase 1 신규 5개 (use_phase1_indicators=True일 때만 search space 포함)
    if use_phase1_indicators:
        w_obv_raw = trial.suggest_float("weight_obv", 0.05, 1.0)
        w_mfi_raw = trial.suggest_float("weight_mfi", 0.05, 1.0)
        w_vwap_raw = trial.suggest_float("weight_vwap", 0.05, 1.0)
        w_volume_spike_raw = trial.suggest_float("weight_volume_spike", 0.05, 1.0)
        w_stoch_rsi_raw = trial.suggest_float("weight_stoch_rsi", 0.05, 1.0)
        total_w = (
            w_rsi_raw + w_macd_raw + w_bb_raw + w_adx_raw
            + w_obv_raw + w_mfi_raw + w_vwap_raw + w_volume_spike_raw + w_stoch_rsi_raw
        )
    else:
        # 4개만 정규화. 신규 5개는 None으로 두면 composite는 자동으로 무시함
        total_w = w_rsi_raw + w_macd_raw + w_bb_raw + w_adx_raw

    # Phase 2: derivatives_weight (use_derivatives=False면 search space에서 제외하고 0 고정)
    if use_derivatives:
        derivatives_weight = trial.suggest_float("derivatives_weight", 0.0, 0.5, step=0.05)
    else:
        derivatives_weight = 0.0

    return CompositeBacktestParams(
        symbol=base_params.symbol,
        interval=base_params.interval,
        start_date=base_params.start_date,
        end_date=base_params.end_date,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        initial_capital=base_params.initial_capital,
        long_threshold=float(long_threshold),
        short_threshold=float(short_threshold),
        leverage=float(leverage),
        position_size_pct=position_size_pct,
        score_exit_buffer=float(score_exit_buffer),
        macro_weight=macro_weight,
        tech_weight_rsi=w_rsi_raw / total_w,
        tech_weight_macd=w_macd_raw / total_w,
        tech_weight_bb=w_bb_raw / total_w,
        tech_weight_adx=w_adx_raw / total_w,
        # 신규 5개: use_phase1_indicators=True일 때만 정규화 가중치, 아니면 None (composite 무시)
        tech_weight_obv=(w_obv_raw / total_w) if use_phase1_indicators else None,
        tech_weight_mfi=(w_mfi_raw / total_w) if use_phase1_indicators else None,
        tech_weight_vwap=(w_vwap_raw / total_w) if use_phase1_indicators else None,
        tech_weight_volume_spike=(w_volume_spike_raw / total_w) if use_phase1_indicators else None,
        tech_weight_stoch_rsi=(w_stoch_rsi_raw / total_w) if use_phase1_indicators else None,
        derivatives_weight=derivatives_weight,
    )


# ---------------------------------------------------------------------------
# 단일 window 실행
# ---------------------------------------------------------------------------

def _run_with_period(
    full_df: pd.DataFrame,
    params: CompositeBacktestParams,
    macro_bullish: float,
    start_iso: str,
    end_iso: str,
    deriv_df: pd.DataFrame | None = None,
    macro_series: pd.Series | None = None,
) -> dict[str, Any]:
    """params를 복제해 start_date/end_date를 지정한 후 _run_backtest_sync 실행."""
    # dataclass 복사 + 기간만 갈아끼움 (Phase 1+2: 18개 필드)
    p = CompositeBacktestParams(
        symbol=params.symbol,
        interval=params.interval,
        start_date=start_iso,
        end_date=end_iso,
        stop_loss_pct=params.stop_loss_pct,
        take_profit_pct=params.take_profit_pct,
        initial_capital=params.initial_capital,
        long_threshold=params.long_threshold,
        short_threshold=params.short_threshold,
        leverage=params.leverage,
        position_size_pct=params.position_size_pct,
        score_exit_buffer=params.score_exit_buffer,
        macro_weight=params.macro_weight,
        tech_weight_rsi=params.tech_weight_rsi,
        tech_weight_macd=params.tech_weight_macd,
        tech_weight_bb=params.tech_weight_bb,
        tech_weight_adx=params.tech_weight_adx,
        tech_weight_obv=params.tech_weight_obv,
        tech_weight_mfi=params.tech_weight_mfi,
        tech_weight_vwap=params.tech_weight_vwap,
        tech_weight_volume_spike=params.tech_weight_volume_spike,
        tech_weight_stoch_rsi=params.tech_weight_stoch_rsi,
        derivatives_weight=params.derivatives_weight,
    )
    return _run_backtest_sync(full_df, p, macro_bullish, deriv_df=deriv_df, macro_series=macro_series)


def run_single_window(
    full_df: pd.DataFrame,
    base_params: CompositeBacktestParams,
    macro_bullish: float,
    window: dict[str, str],
    n_trials: int,
    progress_cb: Callable[[int, int], None] | None = None,
    deriv_df: pd.DataFrame | None = None,
    use_derivatives: bool = True,
    use_phase1_indicators: bool = False,
    macro_series: pd.Series | None = None,
) -> dict[str, Any]:
    """단일 expanding window: IS에서 best params 찾고 OOS에서 적용.

    Args:
        full_df: 전체 OHLCV.
        base_params: symbol/interval/initial_capital 원본.
        macro_bullish: 매크로 점수 (단순화: 윈도우별 동일 값).
        window: make_expanding_windows의 한 항목.
        n_trials: Optuna trial 수.
        progress_cb: (current_trial, total_trials) 콜백.

    Returns:
        index/is_period/oos_period/best_params/is_metrics/oos_metrics.
    """
    # Optuna는 verbose 로깅이 너무 많아 INFO로 제한
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    is_start = window["is_start"]
    is_end = window["is_end"]
    oos_start = window["oos_start"]
    oos_end = window["oos_end"]

    # study 직접 만들고 sampler 시드 고정 → 재현성
    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=20)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    counter = {"n": 0}

    def _objective(trial: optuna.Trial) -> float:
        params = define_search_space(
            trial, base_params,
            use_derivatives=use_derivatives,
            use_phase1_indicators=use_phase1_indicators,
        )
        result = _run_with_period(
            full_df, params, macro_bullish, is_start, is_end,
            deriv_df=deriv_df, macro_series=macro_series,
        )
        if "error" in result:
            return -10000.0  # 에러 case 강하게 회피
        metrics = compute_metrics(result)
        # trial에 메트릭 사용자 속성 첨부 — top combinations 분석용
        for k, v in metrics.items():
            trial.set_user_attr(k, v)
        counter["n"] += 1
        if progress_cb:
            progress_cb(counter["n"], n_trials)
        return score_for_optuna(metrics)

    study.optimize(_objective, n_trials=n_trials, gc_after_trial=False)

    best_params_kv = dict(study.best_trial.params)

    # IS 메트릭 (best trial의 user_attrs)
    is_metrics = {
        k: v for k, v in study.best_trial.user_attrs.items()
        if k in {"expectancy", "profit_factor", "max_drawdown_pct", "win_rate",
                 "trade_count", "avg_win_pct", "avg_loss_pct", "total_return_pct"}
    }

    # best params로 OOS 평가 — search space에 포함된 weight만 정규화 (use_phase1_indicators 자동 감지)
    raw_w_rsi = best_params_kv["weight_rsi"]
    raw_w_macd = best_params_kv["weight_macd"]
    raw_w_bb = best_params_kv["weight_bb"]
    raw_w_adx = best_params_kv["weight_adx"]
    # 신규 5개는 trial에 포함됐을 때만 키 존재 (use_phase1_indicators=True 시점)
    has_phase1 = "weight_obv" in best_params_kv
    if has_phase1:
        raw_w_obv = best_params_kv["weight_obv"]
        raw_w_mfi = best_params_kv["weight_mfi"]
        raw_w_vwap = best_params_kv["weight_vwap"]
        raw_w_volume_spike = best_params_kv["weight_volume_spike"]
        raw_w_stoch_rsi = best_params_kv["weight_stoch_rsi"]
        total_w = (
            raw_w_rsi + raw_w_macd + raw_w_bb + raw_w_adx
            + raw_w_obv + raw_w_mfi + raw_w_vwap + raw_w_volume_spike + raw_w_stoch_rsi
        )
    else:
        total_w = raw_w_rsi + raw_w_macd + raw_w_bb + raw_w_adx

    oos_params = CompositeBacktestParams(
        symbol=base_params.symbol,
        interval=base_params.interval,
        start_date=oos_start,
        end_date=oos_end,
        stop_loss_pct=best_params_kv["stop_loss_pct"],
        take_profit_pct=best_params_kv["take_profit_pct"],
        initial_capital=base_params.initial_capital,
        long_threshold=float(best_params_kv["long_threshold"]),
        short_threshold=float(best_params_kv["short_threshold"]),
        leverage=float(best_params_kv["leverage"]),
        position_size_pct=best_params_kv["position_size_pct"],
        score_exit_buffer=float(best_params_kv["score_exit_buffer"]),
        macro_weight=best_params_kv["macro_weight"],
        tech_weight_rsi=raw_w_rsi / total_w,
        tech_weight_macd=raw_w_macd / total_w,
        tech_weight_bb=raw_w_bb / total_w,
        tech_weight_adx=raw_w_adx / total_w,
        tech_weight_obv=(raw_w_obv / total_w) if has_phase1 else None,
        tech_weight_mfi=(raw_w_mfi / total_w) if has_phase1 else None,
        tech_weight_vwap=(raw_w_vwap / total_w) if has_phase1 else None,
        tech_weight_volume_spike=(raw_w_volume_spike / total_w) if has_phase1 else None,
        tech_weight_stoch_rsi=(raw_w_stoch_rsi / total_w) if has_phase1 else None,
        derivatives_weight=best_params_kv.get("derivatives_weight", 0.0),
    )
    oos_result = _run_backtest_sync(
        full_df, oos_params, macro_bullish,
        deriv_df=deriv_df, macro_series=macro_series,
    )
    if "error" in oos_result:
        oos_metrics: dict[str, float] = {
            "expectancy": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0,
            "win_rate": 0.0, "trade_count": 0,
        }
    else:
        oos_metrics = compute_metrics(oos_result)

    # 정규화된 가중치를 best_params에 함께 기록 (UI 노출용)
    best_params_normalized = {
        **best_params_kv,
        "tech_weight_rsi_norm": raw_w_rsi / total_w,
        "tech_weight_macd_norm": raw_w_macd / total_w,
        "tech_weight_bb_norm": raw_w_bb / total_w,
        "tech_weight_adx_norm": raw_w_adx / total_w,
    }
    if has_phase1:
        best_params_normalized.update({
            "tech_weight_obv_norm": raw_w_obv / total_w,
            "tech_weight_mfi_norm": raw_w_mfi / total_w,
            "tech_weight_vwap_norm": raw_w_vwap / total_w,
            "tech_weight_volume_spike_norm": raw_w_volume_spike / total_w,
            "tech_weight_stoch_rsi_norm": raw_w_stoch_rsi / total_w,
        })

    return {
        "is_period": {"start": is_start, "end": is_end},
        "oos_period": {"start": oos_start, "end": oos_end},
        "best_params": best_params_normalized,
        "is_metrics": is_metrics,
        "oos_metrics": oos_metrics,
        "all_trials": [
            {
                "params": dict(t.params),
                "metrics": {
                    k: t.user_attrs.get(k)
                    for k in ("expectancy", "profit_factor", "max_drawdown_pct",
                              "win_rate", "trade_count", "total_return_pct")
                },
                "score": t.value,
            }
            for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE and t.value is not None
        ],
    }


# ---------------------------------------------------------------------------
# 9 windows 통합 + aggregate
# ---------------------------------------------------------------------------

def aggregate_window_results(window_results: list[dict[str, Any]]) -> dict[str, Any]:
    """9 windows OOS 메트릭의 평균과 필터 통과 여부 + top combinations 추출."""
    if not window_results:
        return {"passes_filter": False, "n_windows": 0}

    n = len(window_results)

    def _avg(key: str) -> float:
        vals = [w["oos_metrics"].get(key, 0.0) for w in window_results]
        return float(sum(vals) / n) if n else 0.0

    avg_expectancy = _avg("expectancy")
    avg_pf = _avg("profit_factor")
    avg_mdd = _avg("max_drawdown_pct")
    avg_win_rate = _avg("win_rate")
    avg_trade_count = _avg("trade_count")

    aggregate_metrics = {
        "expectancy": avg_expectancy,
        "profit_factor": avg_pf,
        "max_drawdown_pct": avg_mdd,
        "win_rate": avg_win_rate,
        "trade_count": int(avg_trade_count),
    }

    # 필터 통과 여부: 평균 PF/MDD/trade_count로 판정
    passes = passes_filter(aggregate_metrics) and avg_expectancy > 0

    # Top combinations: 모든 윈도우의 모든 trial을 한 풀에 모아서
    # 필터 통과한 후보 중 expectancy 내림차순 top 10
    all_candidates: list[dict[str, Any]] = []
    for wi, wr in enumerate(window_results):
        for trial in wr.get("all_trials", []):
            metrics = trial.get("metrics") or {}
            if not metrics or metrics.get("trade_count") is None:
                continue
            if not passes_filter(metrics):
                continue
            all_candidates.append({
                "window_index": wi,
                "params": trial["params"],
                "metrics": metrics,
            })
    all_candidates.sort(key=lambda x: x["metrics"].get("expectancy", 0.0), reverse=True)
    top_combinations = all_candidates[:10]

    return {
        "passes_filter": bool(passes),
        "n_windows": n,
        "avg_oos_expectancy": avg_expectancy,
        "avg_oos_profit_factor": avg_pf,
        "avg_oos_mdd": avg_mdd,
        "avg_oos_win_rate": avg_win_rate,
        "avg_oos_trade_count": int(avg_trade_count),
        "top_combinations": top_combinations,
    }


# ---------------------------------------------------------------------------
# 결과 파일 저장 헬퍼
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """원자적 JSON 쓰기 (tmp 파일 → rename)."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    tmp_path.replace(path)


def update_status(job_id: str, **fields: Any) -> None:
    """job 상태 파일을 부분 갱신. 파일이 없으면 새로 생성."""
    path = get_job_path(job_id)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.update(fields)
    _atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------

def run_walk_forward(
    job_id: str,
    base_params: CompositeBacktestParams,
    n_trials: int = 200,
    n_windows: int = 9,
    macro_bullish: float = 55.0,
    is_start_months: int = 3,
    oos_months: int = 1,
    use_derivatives: bool = True,
    use_phase1_indicators: bool = False,
    use_macro_timeseries: bool = True,
) -> dict[str, Any]:
    """Walk-forward 자동 튜닝 실행 (동기, BackgroundTasks/ProcessPool 안에서 호출 권장).

    base_params.symbol/interval/start_date/end_date/initial_capital은 그대로 사용,
    튜닝 대상 12 파라미터는 무시(샘플링됨).

    Returns:
        최종 결과 dict (status='completed' 또는 'failed').
    """
    started_at = datetime.now(timezone.utc).isoformat()
    update_status(
        job_id=job_id,
        status="running",
        started_at=started_at,
        completed_at=None,
        config={
            "n_trials": n_trials,
            "n_windows": n_windows,
            "is_start_months": is_start_months,
            "oos_months": oos_months,
            "symbol": base_params.symbol,
            "interval": base_params.interval,
            "start_date": base_params.start_date,
            "end_date": base_params.end_date,
            "macro_bullish": macro_bullish,
        },
        progress={"current_window": 0, "total_windows": n_windows,
                  "current_trial": 0, "total_trials": n_trials},
        windows=[],
    )

    try:
        # 1) OHLCV 1회 fetch (전체 기간)
        full_df = _fetch_ohlcv(base_params)
        if full_df is None or full_df.empty:
            raise RuntimeError(
                f"OHLCV 데이터 수집 실패: symbol={base_params.symbol}, "
                f"interval={base_params.interval}"
            )
        if len(full_df) < 100:
            raise RuntimeError(f"데이터 부족: {len(full_df)}봉 (최소 100봉 필요)")

        # 1.5) Phase 2: Derivatives (OI + FR) 1회 fetch — 모든 windows 공유
        # use_derivatives=False면 fetch 자체를 건너뜀
        deriv_df = None
        if use_derivatives:
            from dashboard.backend.services.composite_backtest import _fetch_derivatives
            deriv_df = _fetch_derivatives(base_params, full_df.index)
            if deriv_df is not None:
                logger.info("derivatives 데이터 수집됨: %d행", len(deriv_df))
            else:
                logger.info("derivatives 데이터 없음 — Phase 2 비활성")
        else:
            logger.info("use_derivatives=False — Phase 2 건너뜀")

        # 1.6) Phase 3: Macro 시계열 (TGA + M2 + Dominance) 1회 fetch
        macro_series: Any = None
        if use_macro_timeseries:
            try:
                from dashboard.backend.services.macro_collector import fetch_all_macro
                from dashboard.backend.services.macro_score import compute_macro_score_series
                # 기간을 약간 넉넉히 (warmup 포함)
                start_pad = (full_df.index[0] - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
                end_pad = (full_df.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                macro_data = fetch_all_macro(start_date=start_pad, end_date=end_pad)
                if macro_data:
                    macro_series = compute_macro_score_series(macro_data, full_df.index)
                    logger.info(
                        "macro 시계열 생성: 평균=%.2f 표준편차=%.2f keys=%s",
                        macro_series.mean(), macro_series.std(), list(macro_data.keys()),
                    )
                else:
                    logger.info("macro 데이터 비어있음 — 단일값 fallback")
            except Exception as exc:
                logger.warning("macro 시계열 생성 실패: %s — 단일값 fallback", exc)
        else:
            logger.info("use_macro_timeseries=False — 단일값 사용")

        # 2) Expanding windows 정의
        windows = make_expanding_windows(
            full_df,
            n_windows=n_windows,
            is_start_months=is_start_months,
            oos_months=oos_months,
        )
        if not windows:
            raise RuntimeError("expanding window 생성 실패 — 데이터 기간 부족")

        # 3) 각 window별 Optuna study 실행
        window_results: list[dict[str, Any]] = []
        for wi, w in enumerate(windows):
            update_status(
                job_id,
                progress={
                    "current_window": wi + 1,
                    "total_windows": len(windows),
                    "current_trial": 0,
                    "total_trials": n_trials,
                },
            )

            def _progress(cur: int, total: int, _wi: int = wi) -> None:
                # 너무 잦은 디스크 IO 방지 — 매 10 trial마다만 갱신
                if cur % 10 == 0 or cur == total:
                    update_status(
                        job_id,
                        progress={
                            "current_window": _wi + 1,
                            "total_windows": len(windows),
                            "current_trial": cur,
                            "total_trials": total,
                        },
                    )

            wr = run_single_window(
                full_df, base_params, macro_bullish, w, n_trials,
                progress_cb=_progress,
                deriv_df=deriv_df if use_derivatives else None,
                use_derivatives=use_derivatives,
                use_phase1_indicators=use_phase1_indicators,
                macro_series=macro_series,
            )
            wr["index"] = wi
            window_results.append(wr)

            # 누적 windows 저장 (실시간 진행 확인용)
            update_status(
                job_id,
                windows=[
                    {
                        "index": r["index"],
                        "is_period": r["is_period"],
                        "oos_period": r["oos_period"],
                        "best_params": r["best_params"],
                        "is_metrics": r["is_metrics"],
                        "oos_metrics": r["oos_metrics"],
                    }
                    for r in window_results
                ],
            )

        # 4) Aggregate
        aggregate = aggregate_window_results(window_results)

        completed_at = datetime.now(timezone.utc).isoformat()
        update_status(
            job_id,
            status="completed",
            completed_at=completed_at,
            aggregate=aggregate,
        )
        return {"status": "completed", "job_id": job_id, "aggregate": aggregate}

    except Exception as exc:
        logger.exception("walk_forward job %s 실패", job_id)
        update_status(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
        return {"status": "failed", "job_id": job_id, "error": str(exc)}
