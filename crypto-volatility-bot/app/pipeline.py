"""Core analysis pipeline — data collection → analysis → score.

Notification dispatch is handled separately by NotificationDispatcher.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.analyzers.base import AnalysisResult
from app.analyzers.derivatives_analyzer import DerivativesAnalyzer, DerivativesData
from app.analyzers.onchain_analyzer import OnchainAnalyzer, OnchainDataUnavailableError
from app.analyzers.score_aggregator import AggregatedResult, ScoreAggregator
from app.analyzers.sentiment_analyzer import SentimentAnalyzer
from app.analyzers.technical_analyzer import TechnicalAnalyzer
from app.data.data_collector import DataCollector

if TYPE_CHECKING:
    from app.utils.config import Config

logger = logging.getLogger(__name__)


# Type aliases for clarity
AnalysisResults = list[tuple[str, AggregatedResult]]
AnalysisErrors = list[tuple[str, str]]


async def run_analysis(config: Config) -> tuple[AnalysisResults, AnalysisErrors]:
    """Run analysis for all configured symbols.

    Returns (results, errors) where:
      - results: list of (symbol, AggregatedResult) for successful analyses
      - errors: list of (symbol, error_message) for failed symbols
    """
    collector = DataCollector(
        bybit_api_key=config.bybit_api_key,
        bybit_api_secret=config.bybit_api_secret,
    )
    aggregator = ScoreAggregator(weights=config.analysis_weights)

    results: AnalysisResults = []
    errors: AnalysisErrors = []

    fear_greed_data = await collector.fetch_fear_greed()

    for symbol in config.symbols:
        coin = symbol.split("/")[0].lower()
        try:
            result, error = await _analyze_symbol(
                symbol=symbol,
                coin=coin,
                collector=collector,
                aggregator=aggregator,
                fear_greed=fear_greed_data,
            )
            if result is not None:
                results.append((symbol, result))
            if error is not None:
                errors.append((symbol, error))
        except Exception as e:
            logger.error("심볼 분석 실패 %s: %s", symbol, e, exc_info=True)
            errors.append((symbol, str(e)))

    return results, errors


async def _analyze_symbol(
    symbol: str,
    coin: str,
    collector: DataCollector,
    aggregator: ScoreAggregator,
    fear_greed: int | None,
) -> tuple[AggregatedResult | None, str | None]:
    """Analyze a single symbol. Returns (result, error_message)."""
    onchain_analyzer = OnchainAnalyzer()
    technical_analyzer = TechnicalAnalyzer()
    sentiment_analyzer = SentimentAnalyzer()
    derivatives_analyzer = DerivativesAnalyzer()

    # 1. Onchain — 실패 시 NEUTRAL 폴백
    onchain_raw = await collector.fetch_onchain_data(coin)
    _neutral_onchain = AnalysisResult(score=50.0, signal="NEUTRAL", details={"whale_alert": False}, source="onchain")
    if onchain_raw is None:
        logger.warning("CoinMetrics data unavailable for %s, using neutral onchain score", symbol)
        onchain_result = _neutral_onchain
    else:
        try:
            onchain_result = onchain_analyzer.analyze(onchain_raw)
        except OnchainDataUnavailableError as e:
            logger.warning("Onchain analysis failed for %s: %s, using neutral", symbol, e)
            onchain_result = _neutral_onchain

    # 2. OHLCV 기술적 분석 — ccxt 동기 호출을 별도 스레드에서 실행해 이벤트루프 블로킹 방지
    ohlcv_df = await asyncio.to_thread(collector.fetch_ohlcv, symbol)
    ohlcv_4h_df = await asyncio.to_thread(collector.fetch_ohlcv, symbol, "4h", 50)

    if ohlcv_df is not None and len(ohlcv_df) >= 20:
        technical_result = technical_analyzer.analyze(ohlcv_df, df_4h=ohlcv_4h_df)
    else:
        logger.warning("No OHLCV data for %s, using neutral technical score", symbol)
        technical_result = AnalysisResult(score=50.0, signal="NEUTRAL", source="technical")

    # 3. 감성 분석
    sentiment_result = sentiment_analyzer.analyze(
        {"fear_greed_index": fear_greed} if fear_greed is not None else None
    )

    # 4. 파생상품 분석 (OI + FR) — 실패 시 None (NEUTRAL 처리됨)
    derivatives_result: AnalysisResult | None = None
    deriv_raw = await collector.fetch_derivatives(symbol)
    if deriv_raw is not None:
        try:
            deriv_data = DerivativesData(
                oi_current=deriv_raw["oi_current"],
                oi_3d_ago=deriv_raw["oi_3d_ago"],
                funding_rate=deriv_raw["funding_rate"],
                symbol=symbol,
            )
            derivatives_result = derivatives_analyzer.analyze(deriv_data)
        except Exception as e:
            logger.warning("Derivatives analysis failed for %s: %s", symbol, e)
    else:
        logger.debug("Derivatives data unavailable for %s, skipping", symbol)

    # 5. 종합 집계
    aggregated = aggregator.aggregate(
        onchain=onchain_result,
        technical=technical_result,
        sentiment=sentiment_result,
        derivatives=derivatives_result,
    )
    logger.info(
        "Analysis complete for %s: score=%.1f level=%s deriv=%s",
        symbol,
        aggregated.final_score,
        aggregated.alert_level,
        aggregated.details.get("derivatives_signal", "N/A"),
    )

    return aggregated, None
