"""Technical Analyzer — YAML-driven multi-indicator volatility scorer.

Two-layer scoring:
  1. Base volatility score: weighted average of 5 normalized scalar indicators.
  2. Signal boosters: category-gated, HA-filtered event additions.

Signal boost architecture (Pine Script alignment):
  - HA filter gate: boost only applied when Heikin Ashi confirms direction.
  - Category gate: need (Trend|Momentum >= 1) AND (Volatility >= 1).
  - Categories: Trend(3), Momentum(4), Volatility(4).

Final score = clamp(base_score + signal_boost, 0, 100).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd
import yaml

from app.analyzers.base import AnalysisResult, BaseAnalyzer
from app.analyzers.indicators import REGISTRY

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "technical.yaml"
)
_MIN_ROWS = 20


class TechnicalAnalyzer(BaseAnalyzer):
    def __init__(self, config_path: str | None = None) -> None:
        path = config_path or os.path.normpath(_DEFAULT_CONFIG)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self._indicator_configs: dict[str, dict[str, Any]] = raw["indicators"]
        self._signals = raw["signals"]
        self._boosters: dict[str, dict[str, Any]] = raw.get("signal_boosters", {})
        self._ha_filter_cfg: dict[str, Any] = raw.get("ha_filter", {"enabled": False})
        self._category_gate_cfg: dict[str, Any] = raw.get("category_gate", {"enabled": True})
        self._validate_and_normalize_weights()

    def _validate_and_normalize_weights(self) -> None:
        for name, cfg in self._indicator_configs.items():
            if cfg["weight"] < 0:
                raise ValueError(f"Weight for '{name}' must be non-negative, got {cfg['weight']}")

        enabled = {k: v for k, v in self._indicator_configs.items() if v["enabled"]}
        total = sum(c["weight"] for c in enabled.values())
        if total <= 0:
            return
        for cfg in enabled.values():
            cfg["weight"] = cfg["weight"] / total

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> AnalysisResult:
        if len(df) < _MIN_ROWS:
            raise ValueError(f"DataFrame must have at least {_MIN_ROWS} rows, got {len(df)}")

        base_score, details = self._compute_base_score(df)
        boost_total, boost_details = self._compute_signal_boost(df, df_4h=df_4h)

        final_score = self._clamp(base_score + boost_total)
        details["base_score"] = base_score
        details["signal_boost"] = boost_details

        high_th = self._signals["high_threshold"]
        med_th = self._signals["medium_threshold"]
        min_base = self._signals.get("min_base_for_signal", 0)
        min_base_high = self._signals.get("min_base_for_high", min_base)
        require_extreme_high = self._signals.get("require_extreme_for_high", False)
        require_extreme_med = self._signals.get("require_extreme_for_medium", False)

        active_boosters = boost_details.get("active_boosters", {})
        _extreme_set_base = {"rsi_extreme", "rsi_divergence", "sustained_oversold", "mtf_rsi_extreme"}
        # outlier는 critical(full boost)일 때만 극단 조건으로 인정
        _outlier_full_boost = float(self._boosters.get("outlier", {}).get("boost", 12))
        has_extreme = bool(active_boosters.keys() & _extreme_set_base) or (
            active_boosters.get("outlier", 0.0) >= _outlier_full_boost
        )

        can_be_high = (
            final_score >= high_th
            and boost_total > 0
            and base_score >= min_base_high
            and (has_extreme if require_extreme_high else True)
        )
        can_be_med = (
            final_score >= med_th
            and boost_total > 0
            and base_score >= min_base
            and (has_extreme if require_extreme_med else True)
        )

        if can_be_high:
            signal = "HIGH"
        elif can_be_med:
            signal = "MEDIUM"
        else:
            signal = "LOW"

        return AnalysisResult(score=final_score, signal=signal, details=details, source="technical")

    # ------------------------------------------------------------------
    # Layer 1: Base volatility score (existing YAML-driven weighted avg)
    # ------------------------------------------------------------------

    def _compute_base_score(self, df: pd.DataFrame) -> tuple[float, dict[str, Any]]:
        score = 0.0
        details: dict[str, Any] = {}

        for name, cfg in self._indicator_configs.items():
            if not cfg["enabled"]:
                continue
            fn = REGISTRY.get(name)
            if fn is None:
                continue
            raw_val = fn(df, cfg["period"])
            details[name] = raw_val
            norm = self._normalize(raw_val, cfg["normalize"]["min"], cfg["normalize"]["max"])
            score += norm * cfg["weight"]

        return self._clamp(score), details

    # ------------------------------------------------------------------
    # Layer 2: Signal boosters with HA gate + category gate
    # ------------------------------------------------------------------

    def _compute_signal_boost(self, df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> tuple[float, dict[str, Any]]:
        if not self._boosters:
            return 0.0, {}

        ha_mode = self._ha_filter_cfg.get("mode", "simple")
        indicators = self._compute_signal_indicators(df, ha_mode=ha_mode)

        # 4h 지표 계산 (df_4h가 있으면)
        if df_4h is not None and len(df_4h) >= _MIN_ROWS:
            indicators["mtf_4h"] = self._compute_mtf_indicators(df_4h)

        # ── HA filter gate ──────────────────────────────────────────
        ha_passed = True
        ha_direction: str | None = None
        if self._ha_filter_cfg.get("enabled", False):
            ha = indicators["heikin_ashi"]
            if ha["filter_bullish"]:
                ha_direction = "bullish"
            elif ha["filter_bearish"]:
                ha_direction = "bearish"
            else:
                ha_passed = False

        if not ha_passed:
            return 0.0, {
                "active_boosters": {},
                "total_boost": 0.0,
                "ha_filter": "blocked",
                "ha_direction": None,
            }

        # ── Evaluate all enabled boosters ───────────────────────────
        all_results: dict[str, float] = {}
        category_hits: dict[str, list[str]] = {
            "trend": [],
            "momentum": [],
            "volatility": [],
        }

        for name, cfg in self._boosters.items():
            if not cfg.get("enabled", True):
                continue
            boost = self._evaluate_booster(name, cfg, indicators, df, ha_direction=ha_direction)
            if boost > 0:
                all_results[name] = boost
                cat = cfg.get("category")
                # category는 문자열 또는 리스트 모두 지원
                cats = cat if isinstance(cat, list) else [cat]
                for c in cats:
                    if c in category_hits:
                        category_hits[c].append(name)

        # ── Category gate ───────────────────────────────────────────
        category_gate_enabled = self._category_gate_cfg.get("enabled", True)
        if category_gate_enabled:
            has_trend_or_momentum = bool(
                category_hits["trend"] or category_hits["momentum"]
            )
            has_volatility = bool(category_hits["volatility"])
            category_passed = has_trend_or_momentum and has_volatility
        else:
            category_passed = True

        if not category_passed:
            return 0.0, {
                "active_boosters": {},
                "total_boost": 0.0,
                "ha_filter": "passed",
                "ha_direction": ha_direction,
                "category_gate": "blocked",
                "category_hits": {k: v for k, v in category_hits.items() if v},
            }

        max_boost = self._signals.get("max_boost")
        raw_boost = float(sum(all_results.values()))
        total_boost = min(raw_boost, float(max_boost)) if max_boost is not None else raw_boost
        return total_boost, {
            "active_boosters": all_results,
            "total_boost": total_boost,
            "ha_filter": "passed",
            "ha_direction": ha_direction,
            "category_gate": "passed",
            "category_hits": {k: v for k, v in category_hits.items() if v},
        }

    @staticmethod
    def _compute_signal_indicators(df: pd.DataFrame, ha_mode: str = "simple") -> dict[str, Any]:
        from app.analyzers.indicators import (
            adx,
            bollinger_bands,
            heikin_ashi,
            hull_ma,
            macd,
            rsi,
            stoch_rsi,
        )

        rsi_result = rsi.calculate(df)
        rsi_series = rsi_result["rsi_series"]

        # Hull RSI for StochK × HullRSI crossover
        hull_rsi_series = hull_ma.hma(rsi_series, 10)
        hull_rsi_val = (
            float(hull_rsi_series.iloc[-1])
            if not pd.isna(hull_rsi_series.iloc[-1])
            else None
        )

        result: dict[str, Any] = {
            "rsi": rsi_result,
            "macd": macd.calculate(df),
            "stoch_rsi": stoch_rsi.calculate(df, hull_rsi_value=hull_rsi_val),
            "bb": bollinger_bands.calculate(df),
            "adx": adx.calculate(df),
            "heikin_ashi": heikin_ashi.calculate(df, mode=ha_mode),
        }

        # ── Hull MA crossover (MHULL/SHULL) ─────────────────────────
        close = df["close"]
        mhull = hull_ma.hma(close, 30)
        shull = hull_ma.hma(close, 10)
        result["hull_ma"] = {"mhull": mhull, "shull": shull}

        # ── RSI Trend Line crossover (frsi/srsi) ───────────────────
        frsi = hull_ma.hma(rsi_series, 10)
        srsi = hull_ma.hma(rsi.calculate(df, period=28)["rsi_series"], 10)
        result["rsi_trend"] = {"frsi": frsi, "srsi": srsi}

        # ── ATR series for spike detection ──────────────────────────
        high, low = df["high"], df["low"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        alpha = 1.0 / 14
        result["_atr_series"] = tr.ewm(alpha=alpha, min_periods=14, adjust=False).mean()

        return result

    @staticmethod
    def _compute_mtf_indicators(df_4h: pd.DataFrame) -> dict[str, Any]:
        """4h 타임프레임 지표 계산 (MTF 부스터용)."""
        from app.analyzers.indicators import bollinger_bands, hull_ma, rsi

        rsi_result = rsi.calculate(df_4h)
        bb_result = bollinger_bands.calculate(df_4h)
        close = df_4h["close"]

        # ATR 시리즈 (4h)
        high, low = df_4h["high"], df_4h["low"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr_series = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()

        # HMA (추세 방향 확인용)
        hma_series = hull_ma.hma(close, 20)

        return {
            "rsi": rsi_result,
            "bb": bb_result,
            "atr_series": atr_series,
            "hma": hma_series,
        }

    def _evaluate_booster(
        self,
        name: str,
        cfg: dict[str, Any],
        indicators: dict[str, Any],
        df: pd.DataFrame,
        ha_direction: str | None = None,
    ) -> float:
        boost = cfg.get("boost", 0)

        if name == "rsi_extreme":
            rsi_series = indicators["rsi"]["rsi_series"]
            rsi_val = float(rsi_series.iloc[-1])
            ob = cfg.get("overbought", 80.0)
            os_val = cfg.get("oversold", 20.0)
            if rsi_val > ob or rsi_val < os_val:
                # Phase 4: 극단 존 진입 감지 (쿨다운 지원)
                if cfg.get("require_entry", False) and len(rsi_series) >= 2:
                    prev_rsi = float(rsi_series.iloc[-2])
                    if prev_rsi > ob or prev_rsi < os_val:
                        # 직전 봉도 극단 존: 쿨다운 기간 내에 정상 구간을 벗어난 적 없으면 차단
                        cooldown = cfg.get("cooldown_bars", 0)
                        if cooldown > 0:
                            lookback = min(cooldown, len(rsi_series) - 1)
                            prev_slice = rsi_series.iloc[-(lookback + 1):-1]
                            was_normal = ((prev_slice >= os_val) & (prev_slice <= ob)).any()
                            if not was_normal:
                                return 0.0
                        else:
                            return 0.0
                return float(boost)

        elif name == "rsi_divergence":
            if indicators["rsi"]["divergence"] is not None:
                return float(boost)

        elif name == "volume_spike_strong":
            threshold = cfg.get("threshold", 4.0)
            vol = df["volume"]
            avg_vol = vol.rolling(20).mean().iloc[-1]
            if avg_vol > 0 and float(vol.iloc[-1]) / float(avg_vol) > threshold:
                # Phase 5: 거래량 스파이크 시 최소 가격 변동 수반 필요
                min_pct = cfg.get("min_price_change_pct", 0.0)
                if min_pct > 0:
                    last_open = float(df["open"].iloc[-1])
                    last_close = float(df["close"].iloc[-1])
                    if last_open > 0:
                        price_change = abs(last_close - last_open) / last_open * 100.0
                        if price_change < min_pct:
                            return 0.0
                return float(boost)

        elif name == "atr_spike":
            atr_series = indicators["_atr_series"]
            lookback = cfg.get("lookback", 5)
            multiplier = cfg.get("multiplier", 1.5)
            current_atr = atr_series.iloc[-1]
            if len(atr_series) > lookback and not pd.isna(current_atr):
                prev_avg = atr_series.iloc[-(lookback + 1) : -1].mean()
                if prev_avg > 0 and current_atr > prev_avg * multiplier:
                    return float(boost)

        elif name == "bb_expansion":
            bb = indicators["bb"]
            bandwidth_ratio = cfg.get("bandwidth_ratio", 1.3)
            curr_bw = bb["bandwidth"]
            # Phase 3: 직전 1봉 대신 N봉 평균과 비교
            lookback = cfg.get("lookback", 1)
            bw_series = bb.get("bandwidth_series")
            if bw_series is not None and len(bw_series) > lookback:
                prev_bw = float(bw_series.iloc[-(lookback + 1):-1].dropna().mean())
            else:
                prev_bw = bb["bandwidth_prev"]
            if prev_bw > 0 and curr_bw / prev_bw >= bandwidth_ratio:
                return float(boost)

        elif name == "macd_crossover":
            crossover = indicators["macd"]["crossover"]
            if crossover is not None:
                # Phase 1: HA 방향과 크로스 방향 일치 확인
                if cfg.get("require_direction_match", False) and ha_direction is not None:
                    cross_dir = "bullish" if crossover == "golden" else "bearish"
                    if cross_dir != ha_direction:
                        return 0.0
                return float(boost)

        elif name == "hull_ma_crossover":
            hull = indicators["hull_ma"]
            mhull, shull = hull["mhull"], hull["shull"]
            if len(mhull) >= 2 and not pd.isna(mhull.iloc[-1]) and not pd.isna(shull.iloc[-1]):
                curr_m = float(mhull.iloc[-1])
                prev_m = float(mhull.iloc[-2])
                curr_s = float(shull.iloc[-1])
                prev_s = float(shull.iloc[-2])
                # Phase 1: 크로스 방향 결정 후 HA 방향과 일치 확인
                cross_dir: str | None = None
                if prev_m <= prev_s and curr_m > curr_s:
                    cross_dir = "bullish"
                elif prev_m >= prev_s and curr_m < curr_s:
                    cross_dir = "bearish"
                if cross_dir is not None:
                    if cfg.get("require_direction_match", False) and ha_direction is not None:
                        if cross_dir != ha_direction:
                            return 0.0
                    return float(boost)

        elif name == "adx_di_crossover":
            di_cross = indicators["adx"]["di_crossover"]
            if di_cross is not None:
                # Phase 2: ADX 강도 임계값 — 횡보장(ADX < min_adx) DI 크로스 차단
                min_adx = cfg.get("min_adx", 0.0)
                if min_adx > 0 and indicators["adx"]["adx"] < min_adx:
                    return 0.0
                # Phase 1: HA 방향과 DI 크로스 방향 일치 확인
                if cfg.get("require_direction_match", False) and ha_direction is not None:
                    if di_cross != ha_direction:
                        return 0.0
                return float(boost)

        elif name == "rsi_trend_crossover":
            rt = indicators["rsi_trend"]
            frsi, srsi = rt["frsi"], rt["srsi"]
            if (
                len(frsi) >= 2
                and not pd.isna(frsi.iloc[-1])
                and not pd.isna(srsi.iloc[-1])
                and not pd.isna(frsi.iloc[-2])
                and not pd.isna(srsi.iloc[-2])
            ):
                curr_f = float(frsi.iloc[-1])
                prev_f = float(frsi.iloc[-2])
                curr_s_val = float(srsi.iloc[-1])
                prev_s_val = float(srsi.iloc[-2])
                # Phase 1: 크로스 방향 결정 후 HA 방향과 일치 확인
                rsi_cross_dir: str | None = None
                if prev_f <= prev_s_val and curr_f > curr_s_val:
                    rsi_cross_dir = "bullish"
                elif prev_f >= prev_s_val and curr_f < curr_s_val:
                    rsi_cross_dir = "bearish"
                if rsi_cross_dir is not None:
                    if cfg.get("require_direction_match", False) and ha_direction is not None:
                        if rsi_cross_dir != ha_direction:
                            return 0.0
                    return float(boost)

        elif name == "hull_rsi_crossover":
            sr = indicators["stoch_rsi"]
            if sr["hull_rsi_crossover"] is not None:
                return float(boost)

        elif name == "stochrsi_extreme":
            sr = indicators["stoch_rsi"]
            ob = cfg.get("overbought", 80.0)
            os_val = cfg.get("oversold", 20.0)
            if sr["stoch_k"] > ob or sr["stoch_k"] < os_val:
                return float(boost)

        elif name == "bb_middle_break":
            if indicators["bb"]["middle_line_break"] is not None:
                return float(boost)

        elif name == "outlier":
            from app.analyzers.indicators import outlier_detector

            bb = indicators["bb"]
            atr_series = indicators["_atr_series"]
            current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
            lookback = 5
            prev_avg = float(atr_series.iloc[-(lookback + 1) : -1].mean()) if len(atr_series) > lookback else 0.0

            vol = df["volume"]
            avg_vol = vol.rolling(20).mean().iloc[-1]
            vol_ratio = float(vol.iloc[-1]) / float(avg_vol) if avg_vol > 0 else 1.0

            outlier_result = outlier_detector.detect(
                atr_data={"atr": current_atr, "atr_prev_avg": prev_avg},
                bb_data={"percent_b": bb["percent_b"]},
                volume_data={"spike": vol_ratio > 2.5, "volume_ratio": vol_ratio},
                price_df=df,
                config={
                    "atr_spike_multiplier": cfg.get("atr_spike_multiplier", 2.0),
                    "single_candle_pct": cfg.get("single_candle_pct", 5.0),
                },
            )
            critical_only = cfg.get("critical_only", True)
            if outlier_result["is_critical"]:
                return float(boost)
            if not critical_only and outlier_result["is_outlier"]:
                return float(boost) * 0.5

        elif name == "sustained_oversold":
            rsi_series = indicators["rsi"]["rsi_series"]
            threshold = cfg.get("rsi_threshold", 30.0)
            min_bars = cfg.get("min_consecutive", 6)
            min_ratio = cfg.get("min_ratio", 0.7)  # min_bars 중 최소 비율

            if len(rsi_series) < min_bars:
                return 0.0

            # 최근 min_bars봉 중 min_ratio 이상이 threshold 이하인지 확인
            recent = rsi_series.iloc[-min_bars:]
            if (recent <= threshold).mean() < min_ratio:
                return 0.0

            # 횡보 필터: 아래 중 1개 이상 충족해야 트리거
            if cfg.get("require_confirm", True):
                confirmed = False

                # 1) ATR > 20봉 평균 (변동성 유지/확대)
                atr_series = indicators["_atr_series"]
                if not pd.isna(atr_series.iloc[-1]):
                    atr_avg = float(atr_series.iloc[-21:-1].mean())
                    if atr_avg > 0 and float(atr_series.iloc[-1]) > atr_avg:
                        confirmed = True

                # 2) 현재 close < 최근 min_bars봉 저점 (신저점 갱신)
                if not confirmed:
                    lows = df["low"].iloc[-min_bars:-1]
                    if float(df["close"].iloc[-1]) < float(lows.min()):
                        confirmed = True

                # 3) 현재 거래량 > 20봉 평균 (거래량 활발)
                if not confirmed:
                    vol = df["volume"]
                    avg_vol = float(vol.iloc[-21:-1].mean())
                    if avg_vol > 0 and float(vol.iloc[-1]) > avg_vol:
                        confirmed = True

                if not confirmed:
                    return 0.0

            return float(boost)

        # ── Multi-Timeframe (4h) 부스터 ────────────────────────────
        elif name == "mtf_rsi_extreme":
            mtf = indicators.get("mtf_4h")
            if mtf is None:
                return 0.0
            rsi_series = mtf["rsi"]["rsi_series"]
            if len(rsi_series) == 0 or pd.isna(rsi_series.iloc[-1]):
                return 0.0
            rsi_val = float(rsi_series.iloc[-1])
            ob = cfg.get("overbought", 75.0)
            os_val = cfg.get("oversold", 25.0)
            if rsi_val > ob or rsi_val < os_val:
                return float(boost)
            return 0.0

        elif name == "mtf_bb_expansion":
            mtf = indicators.get("mtf_4h")
            if mtf is None:
                return 0.0
            bb = mtf["bb"]
            bw = bb["bandwidth"]
            bw_series = bb["bandwidth_series"].dropna()
            lookback = cfg.get("lookback", 10)
            if len(bw_series) < lookback + 1:
                return 0.0
            avg_bw = float(bw_series.iloc[-(lookback + 1):-1].mean())
            if avg_bw > 0 and bw > avg_bw * cfg.get("bandwidth_ratio", 1.3):
                return float(boost)
            return 0.0

        elif name == "mtf_trend_confirm":
            mtf = indicators.get("mtf_4h")
            if mtf is None:
                return 0.0
            hma = mtf["hma"]
            if len(hma) < 3 or pd.isna(hma.iloc[-1]) or pd.isna(hma.iloc[-2]):
                return 0.0
            hma_rising = float(hma.iloc[-1]) > float(hma.iloc[-2])
            hma_falling = float(hma.iloc[-1]) < float(hma.iloc[-2])
            if cfg.get("require_direction_match", True) and ha_direction:
                if ha_direction == "bullish" and hma_rising:
                    return float(boost)
                if ha_direction == "bearish" and hma_falling:
                    return float(boost)
                return 0.0
            if hma_rising or hma_falling:
                return float(boost)
            return 0.0

        return 0.0
