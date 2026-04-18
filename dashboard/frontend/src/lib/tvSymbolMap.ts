export const TV_SYMBOL_MAP: Record<string, string> = {
  BTC: 'BINANCE:BTCUSDT',
  ETH: 'BINANCE:ETHUSDT',
  SOL: 'BINANCE:SOLUSDT',
  HYPE: 'BYBIT:HYPEUSDT',
  INJ: 'BINANCE:INJUSDT',
  ONDO: 'BINANCE:ONDOUSDT',
}

export const toTvSymbol = (sym: string): string =>
  TV_SYMBOL_MAP[sym] ?? `BINANCE:${sym}USDT`
