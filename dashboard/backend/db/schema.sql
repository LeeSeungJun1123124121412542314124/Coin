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
