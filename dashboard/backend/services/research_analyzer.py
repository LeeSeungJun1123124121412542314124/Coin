"""리서치 탭 자동 분석 서비스 — 8개 카테고리 병렬 분석."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_FLOW_LABELS = {
    "long_entry": "롱 신규 진입",
    "short_entry": "숏 신규 진입",
    "long_exit": "롱 청산",
    "short_exit": "숏 청산",
    "neutral": "중립",
}

STOCK_SENTIMENT_WEIGHTS = (0.5, 0.5)
PUTCALL_BAND = (1.0, 0.5)

# 주식수급 카테고리 — 운영하며 조정
KR_FLOW_BAND = (50_000.0, -50_000.0)   # 외국인+기관 20영업일 누적(억원): +5조 → 0점, -5조 → 100점 선형
KR_VOLUME_BAND = (0.7, 1.5)            # 최근 5영업일/20영업일 거래대금 비율: 0.7 → 0점, 1.5 → 100점 선형
KR_STOCK_FLOW_WEIGHTS = (0.7, 0.3)     # (수급, 거래대금)
_KR_FLOW_WINDOW_ROWS = 20              # 판정 창 = 20영업일
_KR_FLOW_RECENT_ROWS = 5               # 거래대금 최근 구간 = 5영업일


async def analyze_all() -> dict:
    """8개 카테고리 분석을 병렬 실행하여 통합 결과 반환."""
    results = await asyncio.gather(
        _analyze_macro(),
        _analyze_onchain(),
        _analyze_derivatives(),
        _analyze_altcoin(),
        _analyze_technical(),
        _analyze_market(),
        _analyze_stock_sentiment(),
        _analyze_kr_stock_flow(),
        return_exceptions=True,
    )

    categories = []
    names = ["매크로", "온체인", "파생상품", "알트코인", "기술적분석", "시장분석"]
    keys = ["macro", "onchain", "derivatives", "altcoin", "technical", "market"]
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
        "placeholder": True,  # 실제 분석 결과가 아님 — 스냅샷 저장·전일 비교에서 제외
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
        # 풋콜 비율은 하루 늦게 나와 공포탐욕과 날짜가 다를 수 있다 — 각각 기준일을 붙인다
        "summary": f"F&G {fg_score:.1f} ({fg['date'][5:]}) | Put/Call {float(used_pc):.2f} ({pc['date'][5:]})",
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
            (_KR_FLOW_WINDOW_ROWS + 1,),  # 전일 기준 20일 합계 비교용으로 한 행 더
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

    # 판정 창(20영업일) 밖의 한 행은 전일 기준 합계 계산에만 쓴다
    extra_row = flow_rows[_KR_FLOW_WINDOW_ROWS] if len(flow_rows) > _KR_FLOW_WINDOW_ROWS else None
    flow_rows = flow_rows[:_KR_FLOW_WINDOW_ROWS]

    foreign_total = sum(row["foreign_net"] or 0.0 for row in flow_rows)
    institution_total = sum(row["institution_net"] or 0.0 for row in flow_rows)
    flow_total = foreign_total + institution_total

    # 20일 누적은 천천히 움직여 날마다 같아 보인다 — 최신 영업일 값과 전일 대비 변화를 같이 내려준다
    latest, prev = flow_rows[0], flow_rows[1]
    latest_foreign = latest["foreign_net"] or 0.0
    latest_institution = latest["institution_net"] or 0.0
    if extra_row is None:
        flow_total_change = None
    else:
        # 하루 지나면 최신일이 들어오고 가장 오래된 날이 빠진다
        dropped = (extra_row["foreign_net"] or 0.0) + (extra_row["institution_net"] or 0.0)
        flow_total_change = latest_foreign + latest_institution - dropped

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
        "summary": (
            f"{latest['date'][5:]} 외국인 {latest_foreign:+,.0f}억 · 기관 {latest_institution:+,.0f}억"
            f" | 20일 누적 {flow_total / 10_000:+.1f}조 | 거래대금 {volume_ratio:.2f}x"
        ),
        "details": {
            "latest_date": latest["date"],
            "latest_foreign": latest_foreign,
            "latest_institution": latest_institution,
            "prev_date": prev["date"],
            "prev_foreign": prev["foreign_net"] or 0.0,
            "prev_institution": prev["institution_net"] or 0.0,
            "flow_total_20d_change": flow_total_change,
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
        # 원본이 하루치 값을 이틀쯤 늦게 준다 — 언제 값인지 앞에 붙인다
        as_of = raw.get("as_of")
        if as_of:
            summary = f"{as_of[5:]} 기준 · {summary}"
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
            "details": {"signal": signal, "flow_ratio": round(ratio, 3), "inflow": inflow, "outflow": outflow, "as_of": as_of},
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
            tga_day = latest["date"][5:]  # 주간 발표 — 언제 값인지 붙인다
            if tga_yoy < -20:
                signals.append("bullish")
                score_components.append(25)
                parts.append(f"TGA {tga_val:.0f}B$ ({tga_day} 기준 · YoY {tga_yoy:+.1f}% — 유동성 공급)")
            elif tga_yoy > 20:
                signals.append("bearish")
                score_components.append(65)
                parts.append(f"TGA {tga_val:.0f}B$ ({tga_day} 기준 · YoY {tga_yoy:+.1f}% — 유동성 흡수)")
            else:
                score_components.append(45)
                parts.append(f"TGA {tga_val:.0f}B$ ({tga_day} 기준 · YoY {tga_yoy:+.1f}%)")

    # M2 분석
    if isinstance(m2_raw, list) and m2_raw:
        yoy_data = calc_m2_yoy(m2_raw)
        if yoy_data:
            m2_yoy = yoy_data[-1]["yoy_pct"]
            m2_month = f"{int(yoy_data[-1]['date'][5:7])}월"  # 월간 발표 — 몇 월 값인지 붙인다
            if m2_yoy > 5:
                signals.append("bullish")
                score_components.append(25)
                parts.append(f"M2 YoY {m2_yoy:+.1f}% ({m2_month} 기준 · 통화량 확장)")
            elif m2_yoy < -2:
                signals.append("bearish")
                score_components.append(65)
                parts.append(f"M2 YoY {m2_yoy:+.1f}% ({m2_month} 기준 · 통화량 수축)")
            else:
                score_components.append(45)
                parts.append(f"M2 YoY {m2_yoy:+.1f}% ({m2_month} 기준)")

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
