"""리서치 탭 자동 분석 서비스 — 8개 카테고리 병렬 분석."""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import date, datetime, timezone

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_FLOW_LABELS = {
    "long_entry": "롱 신규 진입",
    "short_entry": "숏 신규 진입",
    "long_exit": "롱 청산",
    "short_exit": "숏 청산",
    "neutral": "중립",
}

# 사람이 9개 시그널을 마지막으로 검토한 UTC 날짜 (수동 갱신 기준일)
SEMICONDUCTOR_SIGNALS_AS_OF = "2026-07-04"
# as_of가 이 일수를 초과하면 direction_watch가 '갱신 필요' 알림을 발송
_SEMI_STALE_DAYS = 21
STOCK_SENTIMENT_WEIGHTS = (0.5, 0.5)
PUTCALL_BAND = (1.0, 0.5)

# 주식수급 카테고리 — 운영하며 조정
KR_FLOW_BAND = (50_000.0, -50_000.0)   # 외국인+기관 20영업일 누적(억원): +5조 → 0점, -5조 → 100점 선형
KR_VOLUME_BAND = (0.7, 1.5)            # 최근 5영업일/20영업일 거래대금 비율: 0.7 → 0점, 1.5 → 100점 선형
KR_STOCK_FLOW_WEIGHTS = (0.7, 0.3)     # (수급, 거래대금)
_KR_FLOW_WINDOW_ROWS = 20              # 판정 창 = 20영업일
_KR_FLOW_RECENT_ROWS = 5               # 거래대금 최근 구간 = 5영업일

# 외국인 4주 누적 순매수 임계값 (조원) — 운영하며 조정
FOREIGN_FLOW_RED_KRW = -3.0     # 누적 ≤ -3조원 → red "경보"
FOREIGN_FLOW_YELLOW_KRW = 0.0   # 누적 < 0원 → yellow "순매도 진행", ≥ 0원 → green "아직 아님"
FLOW_STALE_CALENDAR_DAYS = 7    # 최신 행이 이보다 오래되면 수집 중단 의심 → 수동 폴백
_FLOW_WINDOW_ROWS = 20          # 4주 = 20영업일
# 자동 판정 대상 시그널 id ↔ 종목코드
_FLOW_SIGNAL_TICKERS = {
    "samsung_foreign_selling": "005930",
    "hynix_foreign_selling": "000660",
}

# 반도체 사이클 정점 시그널 — 업황 공통 3 + 삼성 3 + 하이닉스 3. 수동 갱신 상수.
SEMICONDUCTOR_SIGNALS = [
    {
        "key": "industry",
        "name": "업황 공통",
        "signals": [
            {"id": "dram_price_momentum", "name": "DRAM 고정거래가 모멘텀 둔화", "status": "yellow", "label": "둔화 진행", "note": "Q1 +95% → Q2 +48~63% → Q3 +40~50%, 증가율 3분기째 감소"},
            {"id": "lta_price_floor",     "name": "LTA 가격 하한선 무력화",       "status": "green",  "label": "아직 아님", "note": "공급사 계약기간 단축·가격결정권 회복, 영업이익률 40~50%"},
            {"id": "dram_inventory",      "name": "DRAM 재고 증가",               "status": "green",  "label": "아직 아님", "note": "역대 최저 2~3주(하이닉스 2주), 2026년 물량 완판"},
        ],
    },
    {
        "key": "samsung",
        "name": "삼성전자 005930",
        "signals": [
            {"id": "samsung_foreign_selling", "name": "외국인 4주 누적 순매도",        "status": "red",    "label": "경보",     "note": "6월 -20.6조 순매도, 인버스 ETF 매수 전환"},
            {"id": "samsung_eps_consensus",   "name": "EPS 컨센서스 상향 정체/하향",   "status": "green",  "label": "아직 아님", "note": "2Q 컨센 폭증(영업이익 전년比 18배), 상향 진행"},
            {"id": "samsung_capex",           "name": "메모리 capex 폭발적 증가",      "status": "yellow", "label": "진행 중",   "note": "2026 730억달러, 평택 P5 60조 증설"},
        ],
    },
    {
        "key": "hynix",
        "name": "SK하이닉스 000660",
        "signals": [
            {"id": "hynix_foreign_selling", "name": "외국인 4주 누적 순매도",        "status": "red",    "label": "경보",     "note": "6월 -15.9조 순매도"},
            {"id": "hynix_eps_consensus",   "name": "EPS 컨센서스 상향 정체/하향",   "status": "green",  "label": "아직 아님", "note": "2Q 컨센 폭증(영업이익 전년比 6.9배), 상향 진행"},
            {"id": "hynix_capex",           "name": "메모리 capex 폭발적 증가",      "status": "yellow", "label": "진행 중",   "note": "2026 170억달러+, 청주 M15X 20조"},
        ],
    },
]


def _flat_signals() -> list[dict]:
    return [s for sec in SEMICONDUCTOR_SIGNALS for s in sec["signals"]]


def _aggregate_signals(signals: list[dict]) -> dict:
    """시그널 상태를 카드 종합 지표로 집계 (level 임계 로직 유지)."""
    red = sum(1 for s in signals if s["status"] == "red")
    yellow = sum(1 for s in signals if s["status"] == "yellow")
    total = len(signals)
    peak_count = yellow + red
    if red >= 1:
        level = "critical"
    elif yellow >= 3:
        level = "warning"
    elif yellow >= 1:
        level = "neutral"
    else:
        level = "bullish"
    score = (yellow * 50 + red * 100) // total if total else 0
    score = max(0, min(100, score))
    return {"peak_count": peak_count, "total": total, "level": level, "score": score}


def semiconductor_stale_status(today: date | None = None) -> dict:
    """반도체 시그널 데이터의 신선도 판정 (순수). as_of 초과 시 is_stale=True."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    days_since = (today - date.fromisoformat(SEMICONDUCTOR_SIGNALS_AS_OF)).days
    agg = _aggregate_signals(_flat_signals())
    return {
        "as_of": SEMICONDUCTOR_SIGNALS_AS_OF,
        "days_since": days_since,
        "threshold_days": _SEMI_STALE_DAYS,
        "is_stale": days_since > _SEMI_STALE_DAYS,
        "peak_count": agg["peak_count"],
        "total": agg["total"],
        "level": agg["level"],
    }


async def analyze_all() -> dict:
    """8개 카테고리 분석을 병렬 실행하여 통합 결과 반환."""
    results = await asyncio.gather(
        _analyze_macro(),
        _analyze_onchain(),
        _analyze_derivatives(),
        _analyze_altcoin(),
        _analyze_technical(),
        _analyze_market(),
        _analyze_whale(),
        _analyze_semiconductor_signals(),
        _analyze_stock_sentiment(),
        _analyze_kr_stock_flow(),
        return_exceptions=True,
    )

    categories = []
    names = ["매크로", "온체인", "파생상품", "알트코인", "기술적분석", "시장분석", "기타", "반도체 정점"]
    keys = ["macro", "onchain", "derivatives", "altcoin", "technical", "market", "whale", "semiconductor_signals"]
    names.append("주식심리")
    keys.append("stock_sentiment")
    names.append("주식수급")
    keys.append("kr_stock_flow")

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("%s 분석 실패: %s", names[i], result)
            categories.append(_error_category(keys[i], names[i]))
        elif result is None:
            categories.append(_error_category(keys[i], names[i]))
        else:
            categories.append(result)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
    }


def _error_category(key: str, name: str) -> dict:
    return {
        "key": key,
        "name": name,
        "level": "neutral",
        "score": 0,
        "title": "데이터 수집 중",
        "summary": "데이터를 가져오는 중입니다. 잠시 후 새로고침해 주세요.",
        "details": {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _score_to_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "warning"
    if score >= 40:
        return "bearish"
    if score <= 25:
        return "bullish"
    return "neutral"


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _clamp_float(value: float) -> float:
    return max(0.0, min(100.0, value))


def _putcall_score(value: float) -> float:
    high, width = PUTCALL_BAND
    return _clamp_float((high - value) / width * 100)


async def _analyze_stock_sentiment() -> dict:
    """주식 F&G와 Put/Call 최신값으로 주식심리 카테고리를 계산한다."""
    from dashboard.backend.db import connection

    with connection.get_db() as conn:
        fg = conn.execute(
            """SELECT date, value, rating, updated_at
               FROM stock_fear_greed
               ORDER BY date DESC
               LIMIT 1"""
        ).fetchone()
        pc = conn.execute(
            """SELECT date, total_pc, equity_pc, index_pc, updated_at
               FROM cboe_putcall
               ORDER BY date DESC
               LIMIT 1"""
        ).fetchone()

    if fg is None or pc is None:
        return _error_category("stock_sentiment", "주식심리")

    used_pc = pc["equity_pc"] if pc["equity_pc"] is not None else pc["total_pc"]
    if used_pc is None:
        return _error_category("stock_sentiment", "주식심리")

    fg_score = float(fg["value"])
    pc_score = _putcall_score(float(used_pc))
    fg_weight, pc_weight = STOCK_SENTIMENT_WEIGHTS
    score = _clamp_score(fg_score * fg_weight + pc_score * pc_weight)
    level = _score_to_level(score)
    source = "equity_pc" if pc["equity_pc"] is not None else "total_pc"

    return {
        "key": "stock_sentiment",
        "name": "주식심리",
        "level": level,
        "score": score,
        "title": f"주식심리 {score}/100",
        "summary": f"F&G {fg_score} | Put/Call {float(used_pc):.2f}",
        "details": {
            "stock_fear_greed": {
                "date": fg["date"],
                "value": fg["value"],
                "rating": fg["rating"],
                "updated_at": fg["updated_at"],
            },
            "putcall": {
                "date": pc["date"],
                "total_pc": pc["total_pc"],
                "equity_pc": pc["equity_pc"],
                "index_pc": pc["index_pc"],
                "updated_at": pc["updated_at"],
                "used_pc": used_pc,
                "source": source,
            },
            "component_scores": {
                "fear_greed": fg_score,
                "putcall": pc_score,
            },
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _analyze_kr_stock_flow() -> dict:
    """KOSPI 외국인·기관 수급과 시장 거래대금으로 주식수급 카테고리를 계산한다."""
    from dashboard.backend.db import connection

    with connection.get_db() as conn:
        flow_rows = conn.execute(
            """SELECT date, foreign_net, institution_net
               FROM kr_investor_flow
               WHERE market = 'KOSPI'
               ORDER BY date DESC
               LIMIT ?""",
            (_KR_FLOW_WINDOW_ROWS,),
        ).fetchall()
        volume_rows = conn.execute(
            """SELECT date, kospi_value, kosdaq_value
               FROM kr_market_volume
               ORDER BY date DESC
               LIMIT ?""",
            (_KR_FLOW_WINDOW_ROWS,),
        ).fetchall()

    sample = min(len(flow_rows), len(volume_rows))
    if sample < _KR_FLOW_WINDOW_ROWS:
        category = _error_category("kr_stock_flow", "주식수급")
        category["title"] = "데이터 적재 중"
        category["summary"] = f"데이터 적재 중 ({sample}/{_KR_FLOW_WINDOW_ROWS}영업일) — 표본이 차면 자동 판정됩니다."
        return category

    foreign_total = sum(row["foreign_net"] or 0.0 for row in flow_rows)
    institution_total = sum(row["institution_net"] or 0.0 for row in flow_rows)
    flow_total = foreign_total + institution_total

    flow_high, flow_low = KR_FLOW_BAND
    flow_score = _clamp_float((flow_high - flow_total) / (flow_high - flow_low) * 100)

    daily_volumes = [(row["kospi_value"] or 0.0) + (row["kosdaq_value"] or 0.0) for row in volume_rows]
    window_avg = sum(daily_volumes) / len(daily_volumes)
    if window_avg <= 0:
        return _error_category("kr_stock_flow", "주식수급")
    recent_avg = sum(daily_volumes[:_KR_FLOW_RECENT_ROWS]) / _KR_FLOW_RECENT_ROWS
    volume_ratio = recent_avg / window_avg
    volume_low, volume_high = KR_VOLUME_BAND
    volume_score = _clamp_float((volume_ratio - volume_low) / (volume_high - volume_low) * 100)

    flow_weight, volume_weight = KR_STOCK_FLOW_WEIGHTS
    score = _clamp_score(flow_score * flow_weight + volume_score * volume_weight)

    return {
        "key": "kr_stock_flow",
        "name": "주식수급",
        "level": _score_to_level(score),
        "score": score,
        "title": f"주식수급 {score}/100",
        "summary": f"외국인+기관 20일 {flow_total / 10_000:+.1f}조 | 거래대금 {volume_ratio:.2f}x",
        "details": {
            "foreign_20d": foreign_total,
            "institution_20d": institution_total,
            "flow_total_20d": flow_total,
            "volume_ratio": round(volume_ratio, 2),
            "window_start": flow_rows[-1]["date"],
            "window_end": flow_rows[0]["date"],
            "component_scores": {
                "flow": flow_score,
                "volume": volume_score,
            },
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 파생상품 ────────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_derivatives")
async def _analyze_derivatives() -> dict:
    from dashboard.backend.services.spf_service import (
        get_today_spf, calc_bearish_score, calc_bullish_score,
        classify_flow,
    )
    from dashboard.backend.collectors.bybit_derivatives import (
        fetch_open_interest, fetch_funding_rate,
    )

    today = get_today_spf()

    if today:
        oi_change_3d = today.get("oi_change_3d") or 0.0
        oi_change_7d = today.get("oi_change_7d") or 0.0
        cum_fr_3d = today.get("cum_fr_3d") or 0.0
        cum_fr_7d = today.get("cum_fr_7d") or 0.0
        oi_consec = today.get("oi_consecutive_up") or 0
        flow = today.get("flow") or classify_flow(oi_change_3d, cum_fr_3d)
        bearish = today.get("bearish_score") or calc_bearish_score(
            oi_change_3d, oi_change_7d, cum_fr_3d, cum_fr_7d, oi_consec, flow
        )
        bullish = today.get("bullish_score") or calc_bullish_score(
            oi_change_3d, cum_fr_3d, cum_fr_7d, flow
        )
    else:
        oi_data, fr_data = await asyncio.gather(
            fetch_open_interest("BTCUSDT"),
            fetch_funding_rate("BTCUSDT"),
            return_exceptions=True,
        )
        oi_change_3d = 0.0
        cum_fr_3d = fr_data.get("funding_rate", 0.0) * 3 if isinstance(fr_data, dict) else 0.0
        cum_fr_7d = cum_fr_3d * 2
        oi_change_7d = 0.0
        oi_consec = 0
        flow = classify_flow(oi_change_3d, cum_fr_3d)
        bearish = calc_bearish_score(oi_change_3d, oi_change_7d, cum_fr_3d, cum_fr_7d, oi_consec, flow)
        bullish = calc_bullish_score(oi_change_3d, cum_fr_3d, cum_fr_7d, flow)

    score = bearish
    level = _score_to_level(score)
    flow_label = _FLOW_LABELS.get(flow, flow)
    oi_pct = oi_change_3d * 100
    fr_pct = cum_fr_3d * 100

    title = f"{flow_label} — 하락점수 {bearish}/반등점수 {bullish}"
    parts = []
    if oi_change_3d:
        parts.append(f"3일 OI {oi_pct:+.1f}%")
    if cum_fr_3d:
        parts.append(f"누적 FR {fr_pct:+.4f}%")
    if bearish >= 55:
        parts.append("롱 과밀집 경계")
    elif bullish >= 55:
        parts.append("숏 과밀집 → 반등 기대")
    summary = " | ".join(parts) if parts else "데이터 수집 중"

    return {
        "key": "derivatives",
        "name": "파생상품",
        "level": level,
        "score": score,
        "title": title,
        "summary": summary,
        "details": {
            "flow": flow_label,
            "bearish_score": bearish,
            "bullish_score": bullish,
            "oi_change_3d": round(oi_pct, 2),
            "oi_change_7d": round(oi_change_7d * 100, 2),
            "cum_fr_3d": round(fr_pct, 4),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 기술적분석 ──────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_technical")
async def _analyze_technical() -> dict:
    loop = asyncio.get_running_loop()

    def _run() -> dict | None:
        try:
            from app.data.data_collector import DataCollector
            from app.analyzers.technical_analyzer import TechnicalAnalyzer

            collector = DataCollector()
            df = collector.fetch_ohlcv("BTC/USDT", "1h", 200)
            if df is None or df.empty:
                return None

            analyzer = TechnicalAnalyzer()
            result = analyzer.analyze(df)
            if result is None:
                return None

            score = int(result.score)
            signal = result.signal  # HIGH / MEDIUM / LOW
            details = result.details or {}

            level_map = {"HIGH": "critical", "MEDIUM": "warning", "LOW": "neutral"}
            level = level_map.get(signal, "neutral")

            rsi = details.get("rsi")
            bb_pos = details.get("bb")
            signal_boost = details.get("signal_boost", {})
            active_boosters = signal_boost.get("active_boosters", [])

            parts = [f"변동성 점수 {score}/100", f"시그널 {signal}"]
            if rsi is not None:
                parts.append(f"RSI {rsi:.1f}")
            if active_boosters:
                booster_keys = list(active_boosters.keys()) if isinstance(active_boosters, dict) else active_boosters
                parts.append(f"부스터: {', '.join(booster_keys[:3])}")

            return {
                "score": score,
                "signal": signal,
                "level": level,
                "title": f"변동성 {signal} — 기술점수 {score}/100",
                "summary": " | ".join(parts),
                "details": {
                    "score": score,
                    "signal": signal,
                    "rsi": round(rsi, 1) if rsi else None,
                    "bb_position": round(bb_pos, 3) if bb_pos else None,
                    "active_boosters": dict(list(active_boosters.items())[:5]) if isinstance(active_boosters, dict) else active_boosters[:5],
                },
            }
        except Exception as e:
            logger.error("기술적분석 실패: %s", e)
            return None

    result = await loop.run_in_executor(None, _run)
    if result is None:
        return _error_category("technical", "기술적분석")

    return {
        "key": "technical",
        "name": "기술적분석",
        "level": result["level"],
        "score": result["score"],
        "title": result["title"],
        "summary": result["summary"],
        "details": result["details"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 시장분석 ────────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_market")
async def _analyze_market() -> dict:
    from dashboard.backend.api.market_routes import _get_dashboard_snapshot
    from dashboard.backend.services.market_insight import (
        generate_insights, LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_BEARISH, LEVEL_BULLISH,
    )

    dashboard_data = await _get_dashboard_snapshot()
    insights = generate_insights(dashboard_data)

    level_score = {LEVEL_CRITICAL: 85, LEVEL_WARNING: 65, LEVEL_BEARISH: 55, LEVEL_BULLISH: 25, "neutral": 45}

    if insights:
        top = insights[0]
        top_level = top.get("level", "neutral")
        score = level_score.get(top_level, 45)
        title = top.get("title", "시장 분석")
        summary_parts = [ins.get("body", "") for ins in insights[:3] if ins.get("body")]
        summary = " / ".join(summary_parts) if summary_parts else "수집된 데이터 분석 중"
    else:
        top_level = "neutral"
        score = 45
        title = "시장 중립"
        summary = "특이 시그널 없음"

    return {
        "key": "market",
        "name": "시장분석",
        "level": top_level,
        "score": score,
        "title": title,
        "summary": summary,
        "details": {"insights": insights},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 온체인 ─────────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_onchain")
async def _analyze_onchain() -> dict:
    try:
        from app.data.data_collector import DataCollector
        from app.analyzers.onchain_analyzer import OnchainAnalyzer

        collector = DataCollector()
        raw = await collector.fetch_onchain_data("btc")
        if not raw:
            return _error_category("onchain", "온체인")

        analyzer = OnchainAnalyzer()
        result = analyzer.analyze(raw)
        if result is None:
            return _error_category("onchain", "온체인")

        score = int(result.score)
        signal = result.signal  # HIGH_SELL_PRESSURE / ACCUMULATION / NEUTRAL
        details = result.details or {}

        signal_labels = {
            "HIGH_SELL_PRESSURE": ("warning", "거래소 유입 급증 — 매도 압력"),
            "ACCUMULATION": ("bullish", "거래소 유출 — 고래 축적 신호"),
            "NEUTRAL": ("neutral", "온체인 중립"),
        }
        level, title = signal_labels.get(signal, ("neutral", "온체인 분석"))

        inflow = details.get("inflow", 0)
        outflow = details.get("outflow", 0)
        ratio = details.get("flow_ratio") or (inflow / outflow if outflow else 1.0)

        summary = f"유입/유출 비율 {ratio:.2f} | 유입 {inflow:.0f} BTC | 유출 {outflow:.0f} BTC"
        if signal == "HIGH_SELL_PRESSURE":
            summary += " — 매도 우위 주의"
        elif signal == "ACCUMULATION":
            summary += " — 축적 구간 신호"

        return {
            "key": "onchain",
            "name": "온체인",
            "level": level,
            "score": score,
            "title": title,
            "summary": summary,
            "details": {"signal": signal, "flow_ratio": round(ratio, 3), "inflow": inflow, "outflow": outflow},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("온체인 분석 실패: %s", e)
        return _error_category("onchain", "온체인")


# ─── 매크로 ─────────────────────────────────────────────────────────

@cached(ttl=86400, key_prefix="research_macro")
async def _analyze_macro() -> dict:
    from dashboard.backend.collectors.fred import fetch_tga, fetch_m2, fetch_soma, calc_tga_yoy, calc_m2_yoy
    from dashboard.backend.collectors.yahoo_finance import fetch_us_market
    from dashboard.backend.collectors.treasury import fetch_upcoming_auctions

    tga_raw, m2_raw, soma_raw, us_market, auctions_raw = await asyncio.gather(
        fetch_tga(), fetch_m2(), fetch_soma(), fetch_us_market(), fetch_upcoming_auctions(28),
        return_exceptions=True,
    )

    signals = []
    score_components = []
    parts = []

    # TGA 분석
    if isinstance(tga_raw, list) and tga_raw:
        yoy_data = calc_tga_yoy(tga_raw)
        if yoy_data:
            latest = yoy_data[-1]
            tga_yoy = latest["yoy_pct"]
            tga_val = latest["value"]
            if tga_yoy < -20:
                signals.append("bullish")
                score_components.append(25)
                parts.append(f"TGA {tga_val:.0f}B$ (YoY {tga_yoy:+.1f}% — 유동성 공급)")
            elif tga_yoy > 20:
                signals.append("bearish")
                score_components.append(65)
                parts.append(f"TGA {tga_val:.0f}B$ (YoY {tga_yoy:+.1f}% — 유동성 흡수)")
            else:
                score_components.append(45)
                parts.append(f"TGA {tga_val:.0f}B$ (YoY {tga_yoy:+.1f}%)")

    # M2 분석
    if isinstance(m2_raw, list) and m2_raw:
        yoy_data = calc_m2_yoy(m2_raw)
        if yoy_data:
            m2_yoy = yoy_data[-1]["yoy_pct"]
            if m2_yoy > 5:
                signals.append("bullish")
                score_components.append(25)
                parts.append(f"M2 YoY {m2_yoy:+.1f}% (통화량 확장)")
            elif m2_yoy < -2:
                signals.append("bearish")
                score_components.append(65)
                parts.append(f"M2 YoY {m2_yoy:+.1f}% (통화량 수축)")
            else:
                score_components.append(45)
                parts.append(f"M2 YoY {m2_yoy:+.1f}%")

    # 미국 시장 지표
    if isinstance(us_market, list):
        us_dict = {r["ticker"]: r for r in us_market}
        vix = us_dict.get("^VIX", {}).get("price")
        dxy = us_dict.get("DX-Y.NYB", {})
        nasdaq = us_dict.get("^IXIC", {})
        gold = us_dict.get("GC=F", {})

        if vix is not None:
            if vix >= 30:
                signals.append("critical")
                score_components.append(85)
                parts.append(f"VIX {vix:.1f} (공포 급등)")
            elif vix >= 20:
                signals.append("warning")
                score_components.append(65)
                parts.append(f"VIX {vix:.1f} (변동성 주의)")
            elif vix < 13:
                signals.append("bullish")
                score_components.append(20)
                parts.append(f"VIX {vix:.1f} (안정)")
            else:
                score_components.append(40)
                parts.append(f"VIX {vix:.1f}")

        if dxy.get("price"):
            dxy_chg = dxy.get("change_pct", 0)
            parts.append(f"DXY {dxy['price']:.1f} ({dxy_chg:+.2f}%)")

        if nasdaq.get("change_pct") is not None:
            chg = nasdaq["change_pct"]
            parts.append(f"NASDAQ {chg:+.2f}%")
            if chg <= -2:
                score_components.append(70)
            elif chg >= 2:
                score_components.append(25)

        if gold.get("price"):
            gold_chg = gold.get("change_pct", 0)
            parts.append(f"금 {gold['price']:.0f}$ ({gold_chg:+.2f}%)")

    upcoming_auctions: list[dict] = []
    if isinstance(auctions_raw, list) and auctions_raw:
        upcoming_auctions = auctions_raw[:12]
        n = len(auctions_raw)
        first = auctions_raw[0]
        ad = first.get("auction_date", "")[:10]
        st = first.get("type") or ""
        term = first.get("term") or ""
        amt_b = first.get("offering_amount_b")
        tail = f" · {amt_b}B$" if amt_b is not None else ""
        parts.append(f"국채 경매 {n}건 예정 (다음 {ad} {st} {term}{tail})".strip())

    score = int(sum(score_components) / len(score_components)) if score_components else 45
    score = max(0, min(100, score))

    if "critical" in signals:
        level = "critical"
    elif signals.count("bearish") + signals.count("warning") > signals.count("bullish"):
        level = "warning" if "warning" in signals else "bearish"
    elif signals.count("bullish") > signals.count("bearish"):
        level = "bullish"
    else:
        level = "neutral"

    title = {
        "critical": "매크로 위험 — 즉각 주의",
        "warning": "매크로 경계 — 변동성 상승",
        "bearish": "매크로 약세 — 유동성 수축",
        "bullish": "매크로 우호 — 유동성 확장",
        "neutral": "매크로 중립",
    }.get(level, "매크로 분석")

    return {
        "key": "macro",
        "name": "매크로",
        "level": level,
        "score": score,
        "title": title,
        "summary": " | ".join(parts) if parts else "FRED/Yahoo Finance 데이터 수집 중",
        "details": {"upcoming_auctions": upcoming_auctions},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 알트코인 ────────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_altcoin")
async def _analyze_altcoin() -> dict:
    from dashboard.backend.collectors.coingecko import fetch_prices, fetch_global

    coins_raw, global_raw = await asyncio.gather(
        fetch_prices(), fetch_global(), return_exceptions=True,
    )

    if not isinstance(coins_raw, list):
        return _error_category("altcoin", "알트코인")

    alts = [c for c in coins_raw if c.get("symbol") != "BTC"]
    btc_dom = None
    if isinstance(global_raw, dict):
        btc_dom = global_raw.get("btc_dominance")

    if not alts:
        return _error_category("altcoin", "알트코인")

    changes = [c.get("change_24h", 0) or 0 for c in alts]
    avg_change = sum(changes) / len(changes) if changes else 0
    up_count = sum(1 for c in changes if c > 0)
    down_count = len(changes) - up_count

    # 점수: 50 기준, 평균 변동률 반영
    score = int(max(0, min(100, 50 + avg_change * 4)))

    if btc_dom is not None:
        if btc_dom >= 60:
            level = "bearish"
            title = f"알트 약세 — BTC 도미넌스 {btc_dom:.1f}%"
        elif btc_dom <= 48:
            level = "bullish"
            title = f"알트 시즌 신호 — BTC 도미넌스 {btc_dom:.1f}%"
        elif avg_change >= 3:
            level = "bullish"
            title = f"알트 상승 모멘텀 — 평균 {avg_change:+.1f}%"
        elif avg_change <= -3:
            level = "bearish"
            title = f"알트 하락 압력 — 평균 {avg_change:+.1f}%"
        else:
            level = "neutral"
            title = f"알트 혼조 — BTC 도미넌스 {btc_dom:.1f}%"
    else:
        level = "bullish" if avg_change > 2 else ("bearish" if avg_change < -2 else "neutral")
        title = f"알트 평균 {avg_change:+.1f}% ({up_count}↑ {down_count}↓)"

    coin_parts = []
    for c in alts:
        chg = c.get("change_24h", 0) or 0
        coin_parts.append(f"{c.get('symbol','')} {chg:+.1f}%")
    dom_str = f" | BTC 도미넌스 {btc_dom:.1f}%" if btc_dom else ""
    summary = " | ".join(coin_parts) + dom_str

    return {
        "key": "altcoin",
        "name": "알트코인",
        "level": level,
        "score": score,
        "title": title,
        "summary": summary,
        "details": {
            "avg_change_24h": round(avg_change, 2),
            "up_count": up_count,
            "down_count": down_count,
            "btc_dominance": btc_dom,
            "coins": [{"symbol": c.get("symbol"), "change_24h": c.get("change_24h")} for c in alts],
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 기타(고래) ──────────────────────────────────────────────────────

@cached(ttl=600, key_prefix="research_whale")
async def _analyze_whale() -> dict:
    from dashboard.backend.collectors.hyperliquid import fetch_top_whale_positions
    from dashboard.backend.db.connection import get_db
    import json as _json

    whales = await fetch_top_whale_positions(10)

    # DB 스냅샷 기반 합의 (whale_routes와 동일 로직)
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT address, positions FROM whale_snapshots
                   WHERE captured_at >= datetime('now', '-2 hours')
                   ORDER BY captured_at DESC"""
            ).fetchall()
    except Exception:
        rows = []

    long_count = short_count = neutral_count = 0
    seen = set()
    top_positions = []

    for row in rows:
        addr = row["address"]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            positions = _json.loads(row["positions"] or "[]")
        except Exception:
            positions = []
        btc_pos = next((p for p in positions if p.get("coin") in ("BTC", "BTCUSDT")), None)
        if btc_pos is None:
            neutral_count += 1
        elif btc_pos.get("side") == "long":
            long_count += 1
            top_positions.append(btc_pos)
        else:
            short_count += 1
            top_positions.append(btc_pos)

    total = long_count + short_count + neutral_count
    if total == 0:
        # 실시간 데이터로 폴백
        for w in whales[:10]:
            btc_pos = next((p for p in w.get("positions", []) if p.get("coin") in ("BTC", "BTCUSDT")), None)
            if btc_pos is None:
                neutral_count += 1
            elif btc_pos.get("side") == "long":
                long_count += 1
            else:
                short_count += 1
        total = long_count + short_count + neutral_count

    long_pct = round(long_count / total * 100, 1) if total else 0
    short_pct = round(short_count / total * 100, 1) if total else 0

    if total == 0:
        consensus = "unknown"
        level = "neutral"
        score = 50
    elif long_count > short_count + neutral_count:
        consensus = "long"
        level = "bullish"
        score = int(long_pct)
    elif short_count > long_count + neutral_count:
        consensus = "short"
        level = "bearish"
        score = int(100 - short_pct)
    else:
        consensus = "neutral"
        level = "neutral"
        score = 50

    title = f"고래 합의: {consensus.upper()} ({long_pct}% 롱 / {short_pct}% 숏)"
    summary = f"추적 고래 {total}명 | 롱 {long_count}명 | 숏 {short_count}명 | 중립 {neutral_count}명"

    return {
        "key": "whale",
        "name": "기타",
        "level": level,
        "score": score,
        "title": title,
        "summary": summary,
        "details": {
            "consensus": consensus,
            "long_count": long_count,
            "short_count": short_count,
            "neutral_count": neutral_count,
            "long_pct": long_pct,
            "short_pct": short_pct,
            "total": total,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 반도체 정점 시그널 ────────────────────────────────────────────

def _stock_flow_overlay(ticker: str, today: date | None = None) -> dict | None:
    """최근 20영업일 누적 외국인 순매수(조원)로 시그널을 자동 판정.

    행 부족·수집 정체 시 None을 반환해 수동 상수값 폴백 (경보 아님, warning 로그만).
    """
    from dashboard.backend.db import connection

    with connection.get_db() as conn:
        rows = conn.execute(
            """SELECT date, foreign_net FROM kr_stock_investor_flow
               WHERE ticker = ? ORDER BY date DESC LIMIT ?""",
            (ticker, _FLOW_WINDOW_ROWS),
        ).fetchall()
    if len(rows) < _FLOW_WINDOW_ROWS:
        logger.warning("종목 수급 오버레이 생략(%s): 행 %d개 < %d", ticker, len(rows), _FLOW_WINDOW_ROWS)
        return None
    if today is None:
        today = datetime.now(timezone.utc).date()
    latest = date.fromisoformat(rows[0]["date"])
    if (today - latest).days > FLOW_STALE_CALENDAR_DAYS:
        logger.warning("종목 수급 오버레이 생략(%s): 최신 행 %s → 수집 정체 의심", ticker, rows[0]["date"])
        return None

    cum = sum(row["foreign_net"] for row in rows) / 10_000  # 억원 → 조원
    if cum <= FOREIGN_FLOW_RED_KRW:
        status, label = "red", "경보"
    elif cum < FOREIGN_FLOW_YELLOW_KRW:
        status, label = "yellow", "순매도 진행"
    else:
        status, label = "green", "아직 아님"
    direction = "순매수" if cum >= 0 else "순매도"
    return {
        "status": status,
        "label": label,
        "note": f"최근 4주 누적 {abs(cum):.1f}조원 {direction} (자동)",
    }


@cached(ttl=86400, key_prefix="research_semiconductor")
async def _analyze_semiconductor_signals() -> dict:
    """삼성·SK하이닉스 반도체 정점 임박 시그널 9개(3섹션) 분석.

    SEMICONDUCTOR_SIGNALS 상수 기반 정적 분석 (수동 갱신).
    외국인 순매도 시그널 2개는 DB 실측(kr_stock_investor_flow)으로 자동 덮어쓴다.
    as_of가 오래되면 direction_watch가 갱신 알림을 발송한다 (수동 7개 기준).
    """
    sections = copy.deepcopy(SEMICONDUCTOR_SIGNALS)
    # 자동화 대상 시그널은 DB 실측으로 오버레이 — 데이터 부족 시 수동값 유지
    for sec in sections:
        for sig in sec["signals"]:
            ticker = _FLOW_SIGNAL_TICKERS.get(sig["id"])
            if not ticker:
                continue
            overlay = _stock_flow_overlay(ticker)
            if overlay:
                sig.update(overlay)
    flat = [s for sec in sections for s in sec["signals"]]
    agg = _aggregate_signals(flat)
    peak_count = agg["peak_count"]
    total = agg["total"]

    # title 생성
    if peak_count > 0:
        title = f"정점 임박 시그널 {peak_count}/{total} 감지"
    else:
        title = f"정점 시그널 없음 — {total}개 정상"

    # summary 생성
    alerted = [s["name"] for s in flat if s["status"] in ("yellow", "red")]
    if alerted:
        if len(alerted) <= 3:
            summary = " · ".join(alerted) + " 모니터링 중"
        else:
            summary = " · ".join(alerted[:3]) + f" 외 {len(alerted)-3}개 모니터링 중"
    else:
        summary = f"모든 {total}개 시그널 정상"

    today = datetime.now(timezone.utc).date()
    days_since = (today - date.fromisoformat(SEMICONDUCTOR_SIGNALS_AS_OF)).days

    return {
        "key": "semiconductor_signals",
        "name": "반도체 정점",
        "level": agg["level"],
        "score": agg["score"],
        "title": title,
        "summary": summary,
        "details": {
            "sections": sections,
            "as_of": SEMICONDUCTOR_SIGNALS_AS_OF,
            "days_since": days_since,
            "peak_count": peak_count,
            "total": total,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
