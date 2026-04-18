/** 심볼 → TradingView 심볼 수동 매핑 (자동 변환으로 커버 안 되는 예외 케이스) */
export const TV_SYMBOL_MAP: Record<string, string> = {
  BTC: 'BINANCE:BTCUSDT',
  ETH: 'BINANCE:ETHUSDT',
  BNB: 'BINANCE:BNBUSDT',
  XRP: 'BINANCE:XRPUSDT',
  SOL: 'BINANCE:SOLUSDT',
  ADA: 'BINANCE:ADAUSDT',
  DOGE: 'BINANCE:DOGEUSDT',
  AVAX: 'BINANCE:AVAXUSDT',
  DOT: 'BINANCE:DOTUSDT',
  MATIC: 'BINANCE:MATICUSDT',
}

/**
 * 심볼을 TradingView 심볼 문자열로 변환.
 * @param sym     기본 심볼 (예: "BTC")
 * @param override  DB에 저장된 커스텀 tv_symbol (있으면 우선 적용)
 */
export const toTvSymbol = (sym: string, override?: string | null): string =>
  override ?? TV_SYMBOL_MAP[sym] ?? `BINANCE:${sym}USDT`
