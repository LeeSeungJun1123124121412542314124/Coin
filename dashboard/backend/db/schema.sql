-- 크립토 인사이트 대시보드 SQLite 스키마

-- SPF 레코드 (탭 3)
CREATE TABLE IF NOT EXISTS spf_records (
    date              TEXT PRIMARY KEY,
    oi                REAL,
    fr                REAL,
    price             REAL,
    oi_change_3d      REAL,
    oi_change_7d      REAL,
    oi_change_14d     REAL,
    price_change_3d   REAL,
    cum_fr_3d         REAL,
    cum_fr_7d         REAL,
    cum_fr_14d        REAL,
    flow              TEXT,
    bearish_score     INTEGER,
    bullish_score     INTEGER,
    oi_consecutive_up INTEGER,
    oi_surge_alert    TEXT,
    price_after_3d    REAL,
    price_after_7d    REAL,
    price_after_14d   REAL
);

-- 예측 기록 (탭 3)
CREATE TABLE IF NOT EXISTS predictions (
    date              TEXT PRIMARY KEY,
    direction         TEXT,
    direction_raw     TEXT,
    confidence        INTEGER,
    bullish_score     INTEGER,
    bearish_score     INTEGER,
    up_prob           INTEGER,
    down_prob         INTEGER,
    top_patterns      TEXT,   -- JSON
    reasons           TEXT,   -- JSON
    actual_price_3d   REAL,
    result            TEXT,   -- (구) 3일 판정 'hit'|'miss'|NULL — 하위호환 보존
    result_7d         TEXT,   -- 7일 판정 'hit'|'miss'|'neutral'|NULL
    result_14d        TEXT,   -- 14일 판정
    result_30d        TEXT,   -- 30일 판정
    result_60d        TEXT    -- 60일 판정
);

-- 리서치 글 (탭 4)
CREATE TABLE IF NOT EXISTS research_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    badge         TEXT,
    title         TEXT,
    subtitle      TEXT,
    category      TEXT,
    content       TEXT,
    views         INTEGER DEFAULT 0,
    read_time     INTEGER,
    published_at  TEXT DEFAULT (datetime('now'))
);

-- 방문자 카운터
CREATE TABLE IF NOT EXISTS visitors (
    date        TEXT PRIMARY KEY,
    today_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0
);

-- 거래량 히스토리 (탭 2)
CREATE TABLE IF NOT EXISTS volume_daily (
    date         TEXT PRIMARY KEY,
    upbit_krw    REAL,
    bithumb_krw  REAL,
    krx_krw      REAL,
    crypto_ratio REAL
);

-- 고래 스냅샷 (탭 8)
CREATE TABLE IF NOT EXISTS whale_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at   TEXT DEFAULT (datetime('now')),
    address       TEXT,
    nickname      TEXT,
    account_value REAL,
    pnl           REAL,
    roi           REAL,
    positions     TEXT  -- JSON
);

-- 봇 분석 히스토리 (봇↔대시보드 브릿지 테이블)
-- 봇이 매시간 저장 → 탭 5 시장분석, 탭 3 SPF 보정에 사용
CREATE TABLE IF NOT EXISTS analysis_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    timestamp   TEXT DEFAULT (datetime('now')),
    final_score REAL,
    alert_score REAL,
    alert_level TEXT,
    details     TEXT  -- JSON (지표별 상세)
);

CREATE INDEX IF NOT EXISTS idx_analysis_history_symbol_ts
    ON analysis_history(symbol, timestamp DESC);

-- 김치 프리미엄 히스토리 (2시간 주기 수집)
CREATE TABLE IF NOT EXISTS kimchi_premium_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT DEFAULT (datetime('now')),
    btc_krw     REAL NOT NULL,
    btc_usd     REAL NOT NULL,
    usd_krw     REAL NOT NULL,
    premium_pct REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kimchi_premium_ts
    ON kimchi_premium_history(timestamp DESC);

-- 알림 발송 히스토리
CREATE TABLE IF NOT EXISTS alert_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT DEFAULT (datetime('now')),
    symbol       TEXT NOT NULL,
    alert_level  TEXT NOT NULL,
    alert_score  REAL,
    final_score  REAL,
    details      TEXT,   -- JSON
    message_sent INTEGER DEFAULT 1,
    asset_direction        TEXT,   -- 종목 기술방향 long/short/neutral (nullable)
    market_direction       TEXT,   -- 복합 시장방향 long/short/neutral (nullable)
    market_tilt_confidence REAL,   -- 시장방향 신뢰도 (nullable)
    market_tilt_z          REAL    -- 시장방향 복합 z (nullable)
);

CREATE INDEX IF NOT EXISTS idx_alert_history_ts
    ON alert_history(timestamp DESC);

-- 알림 쿨다운 영속화 (서버 재시작 후에도 쿨다운 유지)
CREATE TABLE IF NOT EXISTS alert_cooldowns (
    key           TEXT PRIMARY KEY,
    last_alerted  TEXT NOT NULL,
    cooldown_type TEXT NOT NULL
);

-- 대시보드 코인 슬롯 (6개 고정 위치)
CREATE TABLE IF NOT EXISTS dashboard_coin_slots (
    position    INTEGER PRIMARY KEY CHECK (position BETWEEN 0 AND 6),
    coin_id     TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    tv_symbol   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO dashboard_coin_slots (position, coin_id, symbol, tv_symbol) VALUES
  (0,'bitcoin','BTC','BINANCE:BTCUSDT'),
  (1,'ethereum','ETH','BINANCE:ETHUSDT'),
  (2,'solana','SOL','BINANCE:SOLUSDT'),
  (3,'hyperliquid','HYPE','BYBIT:HYPEUSDT'),
  (4,'injective-protocol','INJ','BINANCE:INJUSDT'),
  (5,'ondo-finance','ONDO','BINANCE:ONDOUSDT'),
  (6,'ripple','XRP','BINANCE:XRPUSDT');

-- 주식 슬롯 (한국/미국 시장별 5개 고정 위치)
CREATE TABLE IF NOT EXISTS stock_slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    market    TEXT NOT NULL,
    position  INTEGER NOT NULL,
    ticker    TEXT NOT NULL,
    name      TEXT NOT NULL,
    tv_symbol TEXT,
    UNIQUE(market, position)
);

-- 한국 주식 외국인·기관·개인 순매수 (억원)
CREATE TABLE IF NOT EXISTS kr_investor_flow (
    date            TEXT NOT NULL,
    market          TEXT NOT NULL CHECK(market IN ('KOSPI','KOSDAQ')),
    foreign_net     REAL,
    institution_net REAL,
    individual_net  REAL,
    PRIMARY KEY (date, market)
);

-- 한국 시장 일별 거래대금 (조원)
CREATE TABLE IF NOT EXISTS kr_market_volume (
    date         TEXT NOT NULL PRIMARY KEY,
    kospi_value  REAL,
    kosdaq_value REAL
);

-- 종목별 일별 투자자 순매수 금액 (억원, 순매매량×종가 환산) — 반도체 정점 시그널 자동 판정용
CREATE TABLE IF NOT EXISTS kr_stock_investor_flow (
    date            TEXT NOT NULL,   -- KST 거래일
    ticker          TEXT NOT NULL,   -- 6자리 종목코드
    foreign_net     REAL,            -- 외국인 순매수 (억원)
    institution_net REAL,            -- 기관 순매수 (억원)
    PRIMARY KEY (date, ticker)
);

-- 미국 주식 Fear & Greed 지수
CREATE TABLE IF NOT EXISTS stock_fear_greed (
    date       TEXT NOT NULL PRIMARY KEY,
    value      REAL NOT NULL,
    rating     TEXT,
    updated_at TEXT NOT NULL
);

-- CBOE Put/Call 비율
CREATE TABLE IF NOT EXISTS cboe_putcall (
    date       TEXT NOT NULL PRIMARY KEY,
    total_pc   REAL,
    equity_pc  REAL,
    index_pc   REAL,
    updated_at TEXT NOT NULL
);

-- 미국 관심종목 내부자 매매 (SEC EDGAR Form 4, 장내 P/S만)
CREATE TABLE IF NOT EXISTS us_insider_trades (
    accession_no     TEXT NOT NULL,   -- SEC 공시 접수번호
    seq              INTEGER NOT NULL,-- 공시 내 거래 순번
    ticker           TEXT NOT NULL,
    filed_at         TEXT NOT NULL,   -- 공시 접수일
    transaction_date TEXT NOT NULL,
    insider_name     TEXT NOT NULL,
    insider_title    TEXT,
    code             TEXT NOT NULL CHECK(code IN ('P','S')),
    shares           REAL,
    price            REAL,
    value            REAL,            -- shares × price (달러, 매도는 음수)
    PRIMARY KEY (accession_no, seq)
);

-- 미국 기관 보유 (SEC EDGAR 13F-HR, 화이트리스트 기관 × us 슬롯 종목)
CREATE TABLE IF NOT EXISTS us_13f_holdings (
    accession_no  TEXT NOT NULL,
    seq           INTEGER NOT NULL,   -- 원본 infoTable 행 인덱스
    institution   TEXT NOT NULL,
    cik           INTEGER NOT NULL,
    ticker        TEXT NOT NULL,
    issuer_name   TEXT NOT NULL,
    quarter       TEXT NOT NULL,      -- reportDate 'YYYY-MM-DD'
    shares        REAL,
    value_usd     REAL,               -- 2023-01-03+ 접수분 = 달러 단위 (배율 없음)
    put_call      TEXT CHECK(put_call IN ('Call','Put')),
    PRIMARY KEY (accession_no, seq)
);
CREATE INDEX IF NOT EXISTS idx_us_13f_ticker_q ON us_13f_holdings(ticker, quarter);

-- 13F 접수 처리 이력 (0매칭 filing 재수집 방지)
CREATE TABLE IF NOT EXISTS us_13f_filings (
    accession_no  TEXT PRIMARY KEY,
    cik           INTEGER NOT NULL,
    institution   TEXT NOT NULL,
    filed_at      TEXT NOT NULL,
    report_date   TEXT NOT NULL,
    processed_at  TEXT NOT NULL
);

-- 지수 방향 판정 그림자 기록
CREATE TABLE IF NOT EXISTS index_shadow_judgments (
    date            TEXT NOT NULL,
    symbol          TEXT NOT NULL CHECK(symbol IN ('^KS11','^GSPC')),
    indicator       TEXT NOT NULL,
    z               REAL,
    direction       TEXT NOT NULL CHECK(direction IN ('long','short','neutral')),
    price           REAL NOT NULL,
    price_after_7d  REAL,
    price_after_14d REAL,
    price_after_30d REAL,
    result_7d       TEXT,
    result_14d      TEXT,
    result_30d      TEXT,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (date, symbol, indicator)
);

-- 코인 1시간봉 OHLCV
CREATE TABLE IF NOT EXISTS coin_ohlcv_1h (
    symbol      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    PRIMARY KEY (symbol, timestamp)
);

-- 코인 1시간봉 인덱스
CREATE INDEX IF NOT EXISTS idx_coin_ohlcv_1h_symbol_ts ON coin_ohlcv_1h(symbol, timestamp DESC);

-- 자동 백테스트 캐시 (지표별 적중률 1시간 TTL)
CREATE TABLE IF NOT EXISTS auto_backtest_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    horizon_h   INTEGER NOT NULL,
    lookback    INTEGER NOT NULL,
    computed_at TEXT NOT NULL,
    result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_abt_cache ON auto_backtest_cache(symbol, horizon_h, computed_at);

-- 봇 상태 키-값 (방향 전환·헬스 알림의 직전 상태 추적)
CREATE TABLE IF NOT EXISTS bot_state (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

-- ============================================================
-- 지표 리더보드 (포워드 모의투자) — 지표별 가상 포트폴리오
-- ============================================================
-- 지표별 포트폴리오 (시드·현재 현금자본)
CREATE TABLE IF NOT EXISTS paper_portfolios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator    TEXT NOT NULL UNIQUE,
    seed         REAL NOT NULL,
    capital      REAL NOT NULL,          -- 실현 현금 잔고
    leverage_cap REAL NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 현재/과거 포지션 (자산별)
CREATE TABLE IF NOT EXISTS paper_positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolios(id),
    asset        TEXT NOT NULL,
    direction    TEXT NOT NULL CHECK(direction IN ('long','short')),
    qty          REAL NOT NULL,
    entry_price  REAL NOT NULL,
    leverage     REAL NOT NULL,
    liq_price    REAL,
    opened_at    TEXT NOT NULL,
    closed_at    TEXT,
    exit_price   REAL,
    pnl          REAL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed'))
);
CREATE INDEX IF NOT EXISTS idx_paper_pos ON paper_positions(portfolio_id, asset, status);

-- 일별 에쿼티 스냅샷 (리더보드·곡선용)
CREATE TABLE IF NOT EXISTS paper_equity (
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolios(id),
    date         TEXT NOT NULL,
    equity       REAL NOT NULL,
    return_pct   REAL,
    PRIMARY KEY (portfolio_id, date)
);

-- ============================================================
-- 학습 탭 테이블
-- ============================================================

-- 학습 대상 심볼 (백필 상태 포함)
CREATE TABLE IF NOT EXISTS learning_symbols (
    symbol          TEXT PRIMARY KEY,
    listed_at       TEXT,
    added_at        TEXT,
    backfill_status TEXT
);

-- 학습용 캔들 (open_time: epoch ms)
CREATE TABLE IF NOT EXISTS learning_candles (
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL,
    open_time   INTEGER NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    PRIMARY KEY (symbol, interval, open_time)
);

-- 학습용 일별 지표 (as_of: 'YYYY-MM-DD')
CREATE TABLE IF NOT EXISTS learning_metrics (
    metric      TEXT NOT NULL,
    scope       TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    value       REAL,
    source      TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (metric, scope, as_of)
);

-- 수집 실행 이력
CREATE TABLE IF NOT EXISTS learning_collection_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    run_at      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK(status IN ('ok','failed','rate_limited','skipped')),
    reason      TEXT,
    is_retry    INTEGER DEFAULT 0
);

-- 학습 탭 설정 (value: JSON)
CREATE TABLE IF NOT EXISTS learning_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

-- 학습용 가상 계좌 (단일 행)
CREATE TABLE IF NOT EXISTS learning_account (
    id              INTEGER PRIMARY KEY CHECK(id = 1),
    started_at      TEXT,
    initial_usdt    REAL,
    cash_usdt       REAL
);

-- 학습용 포지션
CREATE TABLE IF NOT EXISTS learning_positions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    opened_at           TEXT,
    entry_phase         TEXT,
    first_entry_price   REAL,
    status              TEXT CHECK(status IN ('open','closed')),
    closed_at           TEXT
);

-- 학습용 체결 내역
CREATE TABLE IF NOT EXISTS learning_fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     INTEGER NOT NULL REFERENCES learning_positions(id),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK(side IN ('buy','sell')),
    qty             REAL,
    price           REAL,
    usdt_amount     REAL,
    fee_usdt        REAL,
    executed_at     TEXT,
    phase           TEXT,
    ichimoku_json   TEXT,
    detected_json   TEXT,
    memo            TEXT,
    snapshot_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_learning_fills_position ON learning_fills(position_id);

-- 학습용 사후 리뷰 (horizon별 판정)
CREATE TABLE IF NOT EXISTS learning_reviews (
    position_id     INTEGER NOT NULL REFERENCES learning_positions(id),
    horizon_days    INTEGER NOT NULL,
    suggested       TEXT,
    confirmed       TEXT,
    reason          TEXT,
    close_price     REAL,
    judged_at       TEXT,
    PRIMARY KEY (position_id, horizon_days)
);

-- 리서치 분석 일별 스냅샷 (카드의 어제·7일 전 대비 표시용, date는 KST 날짜)
CREATE TABLE IF NOT EXISTS research_snapshot (
    date       TEXT NOT NULL,
    key        TEXT NOT NULL,
    level      TEXT NOT NULL,
    score      INTEGER NOT NULL,
    title      TEXT NOT NULL,
    summary    TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (date, key)
);
