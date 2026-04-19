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
    result            TEXT    -- 'hit' | 'miss' | NULL(미판정)
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
    message_sent INTEGER DEFAULT 1
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
    position    INTEGER PRIMARY KEY CHECK (position BETWEEN 0 AND 5),
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
  (5,'ondo-finance','ONDO','BINANCE:ONDOUSDT');

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

-- ============================================================
-- 시뮬레이터 테이블
-- ============================================================

-- 시뮬레이터 가상 계좌 (시장별 3개)
CREATE TABLE IF NOT EXISTS sim_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market          TEXT NOT NULL CHECK(market IN ('crypto','kr_stock','us_stock')),
    currency        TEXT NOT NULL,
    capital         REAL NOT NULL,
    initial_capital REAL NOT NULL,
    reset_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 예측 레코드
CREATE TABLE IF NOT EXISTS sim_predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES sim_accounts(id),
    asset_symbol    TEXT NOT NULL,
    mode            TEXT NOT NULL CHECK(mode IN ('direction','target_price','portfolio')),
    direction       TEXT CHECK(direction IN ('long','short')),
    target_price    REAL,
    entry_price     REAL NOT NULL,
    entry_time      TEXT NOT NULL,
    expiry_time     TEXT NOT NULL,
    status          TEXT DEFAULT 'pending' CHECK(status IN ('pending','settled','liquidated','cancelled')),
    indicator_tags  TEXT,   -- JSON 배열
    note            TEXT,
    created_at      TEXT NOT NULL
);

-- 페이퍼 포지션 상세
CREATE TABLE IF NOT EXISTS sim_positions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id       INTEGER NOT NULL REFERENCES sim_predictions(id),
    instrument_type     TEXT NOT NULL CHECK(instrument_type IN ('spot','futures')),
    quantity            REAL NOT NULL,
    leverage            INTEGER DEFAULT 1,
    stop_loss           REAL,
    take_profit         REAL,
    liquidation_price   REAL,
    funding_fee_accrued REAL DEFAULT 0
);

-- 채점 결과
CREATE TABLE IF NOT EXISTS sim_settlements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER NOT NULL REFERENCES sim_predictions(id),
    settled_at      TEXT NOT NULL,
    actual_price    REAL NOT NULL,
    direction_hit   INTEGER,
    price_error     REAL,
    pnl             REAL,
    pnl_pct         REAL,
    mdd             REAL,
    sharpe          REAL,
    liquidated      INTEGER DEFAULT 0
);

-- 펀딩비 차감 이력
CREATE TABLE IF NOT EXISTS sim_funding_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     INTEGER NOT NULL REFERENCES sim_positions(id),
    funding_time    TEXT NOT NULL,
    fr_value        REAL NOT NULL,
    funding_amount  REAL NOT NULL
);

-- 계좌 리셋 이력 (히스토리 영구 보존)
CREATE TABLE IF NOT EXISTS sim_account_resets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES sim_accounts(id),
    reset_at        TEXT NOT NULL,
    capital_before  REAL NOT NULL,
    new_capital     REAL NOT NULL
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

-- 시뮬레이터 인덱스
CREATE INDEX IF NOT EXISTS idx_sim_predictions_account ON sim_predictions(account_id, status);
CREATE INDEX IF NOT EXISTS idx_sim_predictions_expiry ON sim_predictions(expiry_time, status);
CREATE INDEX IF NOT EXISTS idx_sim_settlements_pred ON sim_settlements(prediction_id);
CREATE INDEX IF NOT EXISTS idx_sim_positions_prediction ON sim_positions(prediction_id);
CREATE INDEX IF NOT EXISTS idx_sim_funding_position ON sim_funding_events(position_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sim_accounts_market ON sim_accounts(market);
CREATE INDEX IF NOT EXISTS idx_coin_ohlcv_1h_symbol_ts ON coin_ohlcv_1h(symbol, timestamp DESC);
