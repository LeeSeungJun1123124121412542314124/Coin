"""Core analysis pipeline — data collection → analysis → score.

Notification dispatch is handled separately by NotificationDispatcher.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.analyzers.base import AnalysisResult
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

    fear_greed_data = collector.fetch_fear_greed()

    for symbol in config.symbols:
        coin = symbol.split("/")[0].lower()
        result, error = _analyze_symbol(
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

    return results, errors


def _analyze_symbol(
    symbol: str,
    coin: str,
    collector: DataCollector,
    aggregator: ScoreAggregator,
    fear_greed: int | None,
) -> tuple[AggregatedResult | None, str | None]:
    """Analyze a single symbol. Returns (result, error_message)."""
    # 1. Fetch onchain data — optional; failure uses neutral score (긴급 알림은 기술적 분석만 사용)
    onchain_raw = collector.fetch_onchain_data(coin)
    onchain_analyzer = OnchainAnalyzer()
    technical_analyzer = TechnicalAnalyzer()
    sentiment_analyzer = SentimentAnalyzer()

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

    # 2. Fetch OHLCV — optional; failure uses neutral technical score
    ohlcv_df = collector.fetch_ohlcv(symbol)
    ohlcv_4h_df = collector.fetch_ohlcv(symbol, timeframe="4h", limit=50)

    if ohlcv_df is not None and len(ohlcv_df) >= 20:
        technical_result = technical_analyzer.analyze(ohlcv_df, df_4h=ohlcv_4h_df)
    else:
        logger.warning("No OHLCV data for %s, using neutral technical score", symbol)
        technical_result = AnalysisResult(score=50.0, signal="NEUTRAL", source="technical")

    sentiment_result = sentiment_analyzer.analyze(
        {"fear_greed_index": fear_greed} if fear_greed is not None else None
    )

    # 4. Aggregate
    aggregated = aggregator.aggregate(
        onchain=onchain_result,
        technical=technical_result,
        sentiment=sentiment_result,
    )
    logger.info(
        "Analysis complete for %s: score=%.1f level=%s",
        symbol,
        aggregated.final_score,
        aggregated.alert_level,
    )

    return aggregated, None
