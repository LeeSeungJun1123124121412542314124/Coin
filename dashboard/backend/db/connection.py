"""SQLite 커넥션 관리 — WAL 모드, 스키마 자동 초기화."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = os.getenv("DATABASE_PATH", "crypto.db")
_DB_FALLBACK = "crypto.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_conn: sqlite3.Connection | None = None
# 동시 스케줄 job 간 트랜잭션 간섭 방지용 Lock
_db_lock = threading.Lock()

import logging as _logging
_logger = _logging.getLogger(__name__)


def _resolve_db_path() -> str:
    """DB 경로 확인 — 쓸 수 없으면 fallback 경로 사용."""
    path = _DB_PATH
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # 쓰기 가능 여부 테스트
        test_conn = sqlite3.connect(path)
        test_conn.close()
        return path
    except (OSError, sqlite3.OperationalError):
        _logger.warning("DB 경로 '%s' 사용 불가 → fallback '%s'", path, _DB_FALLBACK)
        return _DB_FALLBACK


def get_connection() -> sqlite3.Connection:
    """싱글톤 커넥션 반환. 없으면 생성 후 스키마 초기화."""
    global _conn
    if _conn is None:
        db_path = _resolve_db_path()
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    # 코인 슬롯 CHECK 제약 마이그레이션: BETWEEN 0 AND 5 → BETWEEN 0 AND 6
    _migrate_coin_slots_constraint(conn)
    # 마이그레이션 후 position 6 기본값 삽입 (schema.sql의 INSERT OR IGNORE는 구 제약 때문에 실패)
    conn.execute(
        "INSERT OR IGNORE INTO dashboard_coin_slots (position, coin_id, symbol, tv_symbol) VALUES (?,?,?,?)",
        (6, 'ripple', 'XRP', 'BINANCE:XRPUSDT'),
    )
    # 시뮬레이터 초기 계좌 생성 (이미 존재하면 무시)
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR IGNORE INTO sim_accounts (id, market, currency, capital, initial_capital, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        [
            (1, 'crypto',   'USDT', 10000.0, 10000.0, now, now),
            (2, 'kr_stock', 'KRW',  10000000.0, 10000000.0, now, now),
            (3, 'us_stock', 'USD',  10000.0, 10000.0, now, now),
        ]
    )
    # 기본 주식 슬롯 초기화 (이미 존재하면 무시)
    conn.executemany(
        "INSERT OR IGNORE INTO stock_slots (market, position, ticker, name, tv_symbol) VALUES (?,?,?,?,?)",
        [
            ('kr', 1, '005930.KS', '삼성전자', 'KRX:005930'),
            ('kr', 2, '000660.KS', 'SK하이닉스', 'KRX:000660'),
            ('kr', 3, '035720.KS', '카카오', 'KRX:035720'),
            ('kr', 4, '005380.KS', '현대차', 'KRX:005380'),
            ('kr', 5, '035420.KS', 'NAVER', 'KRX:035420'),
            ('kr', 6, '373220.KS', 'LG에너지솔루션', 'KRX:373220'),
            ('kr', 7, '068270.KS', '셀트리온', 'KRX:068270'),
            ('us', 1, 'AAPL', 'Apple', 'NASDAQ:AAPL'),
            ('us', 2, 'MSFT', 'Microsoft', 'NASDAQ:MSFT'),
            ('us', 3, 'NVDA', 'NVIDIA', 'NASDAQ:NVDA'),
            ('us', 4, 'TSLA', 'Tesla', 'NASDAQ:TSLA'),
            ('us', 5, 'GOOGL', 'Alphabet', 'NASDAQ:GOOGL'),
            ('us', 6, 'META', 'Meta', 'NASDAQ:META'),
            ('us', 7, 'AMZN', 'Amazon', 'NASDAQ:AMZN'),
        ]
    )
    conn.commit()


def _migrate_coin_slots_constraint(conn: sqlite3.Connection) -> None:
    """dashboard_coin_slots의 CHECK 제약을 BETWEEN 0 AND 5 → BETWEEN 0 AND 6으로 마이그레이션."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='dashboard_coin_slots'"
    ).fetchone()
    if row and 'AND 5' in row[0]:
        conn.executescript("""
            BEGIN;
            CREATE TABLE dashboard_coin_slots_new (
                position    INTEGER PRIMARY KEY CHECK (position BETWEEN 0 AND 6),
                coin_id     TEXT NOT NULL,
                symbol      TEXT NOT NULL,
                tv_symbol   TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO dashboard_coin_slots_new SELECT * FROM dashboard_coin_slots;
            DROP TABLE dashboard_coin_slots;
            ALTER TABLE dashboard_coin_slots_new RENAME TO dashboard_coin_slots;
            COMMIT;
        """)


@contextmanager
def get_db():
    """요청 단위 커넥션 컨텍스트 매니저.

    단일 커넥션을 공유하므로 Lock으로 동시 write 트랜잭션 간섭을 방지한다.
    """
    conn = get_connection()
    with _db_lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
