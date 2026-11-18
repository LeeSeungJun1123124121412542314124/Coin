# 학습 탭 1차 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드에 '학습' 탭을 추가해 바이낸스 현물 차트(일목·와이코프·엘리엇) → 근거 필수 모의매매(10,000 USDT) → 포지션 복기 → 성과(적중률·승률·DCA) 루프를 완성하고, 쓸모없는 수동 모의투자를 백업 후 제거한다.

**Architecture:** 기존 계층 구조(`collectors/` → `jobs/` → `services/` → `api/`, SQLite 단일 DB, APScheduler in-process)를 그대로 따른다. 지표 계산(`learning_indicators.py`)과 성과 계산(`learning_metrics.py`)은 DB를 모르는 순수 함수로 두고, 상태 변경은 `learning_account.py`·`learning_review.py`에 모은다. 프론트는 `Learning.tsx` 한 화면 안에 하위 탭 6개를 두고, 데이터 변환은 테스트 가능한 순수 모듈(`learningChartData.ts`)로 뺀다.

**Tech Stack:** Python 3.12, FastAPI, httpx(AsyncClient), sqlite3, APScheduler, pytest / React 19, TypeScript, lightweight-charts 5, vite, node 내장 test(assert)

**Spec:** `docs/plans/learning-tab-phase1-spec-2026-11-18.md` (Seed `seed_387bc0fe5a21`)

## Global Constraints
- 기준: 바이낸스 현물 USDT 페어. 수수료 `0.001`(0.1%). 시작 자금 `10000.0` USDT. 동시 추적 최대 `5` 종목
- 시간 단위: `1d`, `4h`만. 캔들 시각은 UTC open_time(ms). 아직 마감 안 된 봉은 저장하지 않는다
- 저장소: 기존 SQLite에 테이블 추가. 새 패키지 설치 금지(필요하면 멈추고 사용자 승인)
- 무료 API만: CoinMetrics Community(IP당 6초 10회), mempool.space, DefiLlama, 바이낸스 선물 공개 API, BGeometrics 무료(시간당 8회·하루 15회), 기존 FRED(TGA·M2)
- 수집 시각(UTC): 일봉·온체인 `00:10`, 미갱신 재시도 `04:00`(KST 13:00), 4시간봉 `00,04,08,12,16,20시 05분`
- 수집 실패: 항목 비우고 사유 기록, 체결은 허용, `notify_job_failure("learning:<source>", reason)`로 텔레그램 알림. 알림·로그에 토큰·키 금지
- 국면 값: `accumulation|markup|distribution|markdown|unclear` (화면 표기: 매집·상승·분산·하락·불명확)
- 일목 선택지: `cloud_position: above|inside|below`, `tk_cross: golden|dead|none`(전환선>기준선=golden 상태), `chikou: above|below`, `future_cloud: bullish|bearish`
- 와이코프 기본값 `n=30, width_pct=15.0, vol_mult=2.0`(거래량 기준 직전 20봉). 엘리엇 기본값 `threshold_1d=10.0, threshold_4h=5.0, levels=[0.382,0.5,0.618,1.0,1.618]`. DCA 기본 `symbol="BTCUSDT"`, 52주
- 자동 판정 임계 `5.0`%. 복기 `14`·`28`일, 기준 = 첫 진입일(UTC 날짜), 판정 가격 = 그날 1d 종가
- 원화 환산: 기존 `collectors/exchange_rate.fetch_usd_krw()` 값을 USDT≈USD로 보고 곱한다
- 코드 주석·로그·화면 문구는 한국어. 커밋은 `type: 한국어 설명`, 로컬 커밋만(master push = 자동 배포라 push 금지)
- 테스트 실행: 저장소 루트에서 `.venv/Scripts/python.exe -m pytest <파일> -q -p no:cacheprovider` (CI는 `python -m pytest`)

## 사전 준비 (Task 1 전에)
- 테스트 기준선(2026-11-18, 변경 전): `dashboard/tests` 244 passed, 8 failed. 실패 8개는 모두 로컬 `.venv`에 `slowapi`가 없어 `main.py` import가 안 되는 환경 문제(`requirements-lock.txt`에는 `slowapi==0.1.10` 있음)
- Task 2·10 테스트가 `main._register_jobs`를 import하므로, **사용자 승인 후** `.venv/Scripts/python.exe -m pip install -c requirements-lock.txt slowapi==0.1.10`로 맞추고 기준선을 다시 잰다(목표: 252 passed 또는 기존 실패 사유 기록)

## Review Focus
1. **미마감 봉 저장**: 바이낸스 klines 응답 마지막 봉은 진행 중일 수 있다 → `close_time >= now`인 봉은 버린다 (Task 3 테스트)
2. **긴 백필 중복**: BTC 4시간봉 약 1.9만 봉을 1000개씩 나눠 받는다. 백필을 두 번 돌려도 행 수가 같아야 한다(UPSERT) (Task 3 테스트)
3. **전량 매도 후 잔량**: 부동소수 잔량(1e-12) 때문에 포지션이 안 닫히면 안 된다 → 남은 수량이 `1e-9` 미만이면 0으로 보고 청산 (Task 10 테스트)
4. **복기일 캔들 없음**: 기준일이 오늘이고 09:10 수집 전이면 해당 1d 종가가 없다 → 오류가 아니라 `pending` (Task 11 테스트)
5. **DCA 기준 종목 미추적 / 보유 중 종목 삭제**: 기준 종목 캔들이 없으면 성과 API는 `dca: null`과 사유를 준다. 열린 포지션이 있는 종목은 추적 해제를 거부한다 (Task 4·12 테스트)

---

### Task 1: DB 스키마 추가 + 레거시 수동 모의투자 백업·삭제

**Files:**
- Modify: `dashboard/backend/db/schema.sql` (sim_* 6개 CREATE 제거, learning_* 테이블 추가)
- Modify: `dashboard/backend/db/connection.py` (`_migrate_sim_positions_v2`·`_migrate_sim_funding_unique`·sim 계좌 초기 삽입 제거, `_backup_and_drop_legacy_sim` 추가)
- Test: `dashboard/tests/test_legacy_sim_removal.py`

**Interfaces:**
- Produces: 테이블 `learning_symbols(symbol PK, listed_at, added_at, backfill_status)`, `learning_candles(symbol, interval, open_time INTEGER, open, high, low, close, volume, PK(symbol, interval, open_time))`, `learning_metrics(metric, scope, as_of TEXT 'YYYY-MM-DD', value REAL, source, fetched_at, PK(metric, scope, as_of))`, `learning_collection_runs(id PK, source, run_at, status 'ok|failed|rate_limited|skipped', reason, is_retry INTEGER)`, `learning_settings(key PK, value TEXT JSON)`, `learning_account(id PK CHECK(id=1), started_at, initial_usdt, cash_usdt)`, `learning_positions(id PK, symbol, opened_at, entry_phase, first_entry_price, status 'open|closed', closed_at)`, `learning_fills(id PK, position_id, symbol, side 'buy|sell', qty, price, usdt_amount, fee_usdt, executed_at, phase, ichimoku_json, detected_json, memo, snapshot_json)`, `learning_reviews(position_id, horizon_days, suggested, confirmed, reason, close_price, judged_at, PK(position_id, horizon_days))`
- Produces: `_backup_and_drop_legacy_sim(conn, backup_dir: Path) -> Path | None` — `sim_accounts`가 있으면 6개 테이블(`sim_accounts, sim_predictions, sim_positions, sim_settlements, sim_funding_events, sim_account_resets`) 전체 행을 `{table: [row dict...]}` JSON으로 `backup_dir/legacy_sim_backup_<UTC yyyymmddTHHMMSS>.json`에 쓰고 DROP. 없으면 None. `backup_dir = Path(db_path).parent / "backups"`

- [ ] **Step 1: 실패하는 테스트 작성** (`state_db` 픽스처는 `test_direction_watch.py` 방식 복사)

```python
def test_legacy_tables_backed_up_and_dropped(tmp_path, monkeypatch):
    db = tmp_path / "crypto.db"
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE sim_accounts (id INTEGER PRIMARY KEY, market TEXT, capital REAL)")
    raw.execute("INSERT INTO sim_accounts VALUES (1, 'crypto', 10000)")
    for t in ("sim_predictions","sim_positions","sim_settlements","sim_funding_events","sim_account_resets"):
        raw.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)")
    raw.commit(); raw.close()
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(db)); monkeypatch.setattr(connection, "_conn", None)
    conn = connection.get_connection()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(n.startswith("sim_") for n in names)
    assert {"learning_candles","learning_fills","learning_reviews"} <= names
    backups = list((tmp_path / "backups").glob("legacy_sim_backup_*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["sim_accounts"][0]["capital"] == 10000

def test_no_legacy_tables_no_backup(tmp_path, monkeypatch):  # 새 DB면 백업 파일 안 만듦
    ...
    assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").glob("*.json"))
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/Scripts/python.exe -m pytest dashboard/tests/test_legacy_sim_removal.py -q -p no:cacheprovider` → FAIL (sim_ 테이블 남음 / learning_ 없음)
- [ ] **Step 3: 구현** — `_init_schema`에서 `executescript(schema)` **전에** `_backup_and_drop_legacy_sim(conn, Path(_resolve_db_path()).parent / "backups")` 호출. JSON은 `ensure_ascii=False, indent=1`. sim 관련 migrate 함수와 계좌 초기 삽입을 지운다. 인덱스: `learning_fills(position_id)`, `learning_candles(symbol, interval, open_time)`는 PK로 충분
- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS. 이어서 `.venv/Scripts/python.exe -m pytest dashboard/tests -q -p no:cacheprovider` 실행해 sim 관련 외 실패가 없는지 확인(이 시점엔 `test_settle_predictions.py`·`test_sim_funding.py` 실패는 Task 2에서 정리하므로 허용)
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 테이블 추가 및 수동 모의투자 테이블 백업 후 삭제"`

### Task 2: 레거시 수동 모의투자 코드 제거 (보존 엔드포인트 보호)

**Files:**
- Modify: `dashboard/backend/api/sim_routes.py` — 삭제: `GET/POST /sim/accounts*`, `GET/POST/DELETE /sim/predictions*`, `/sim/scorecard*`, `/sim/positions/{id}`, `/sim/projection`, `/sim/signals`, `/sim/macro-context`, `/sim/win-rate-analysis`와 이들만 쓰던 모델·헬퍼·import. 유지: `/sim/auto-backtest`, `/sim/composite-backtest`, `/sim/tune`, `/sim/tune/{job_id}`, `/sim/leaderboard*`
- Modify: `dashboard/backend/services/sim_engine.py` — `_get_mmr`, `calc_liquidation_price`만 남김(paper_engine이 사용). 나머지 함수 삭제
- Modify: `dashboard/backend/main.py` — `settle_expired_predictions`(id `settle_predictions`)·`_apply_sim_funding`(id `sim_funding`) 잡과 import 제거
- Delete: `dashboard/backend/services/sim_scorecard.py`, `dashboard/backend/jobs/settle_predictions.py`, `dashboard/tests/test_settle_predictions.py`, `dashboard/tests/test_sim_funding.py`
- Delete(조건부): `services/return_projector.py`, `services/signal_analyzer.py` — `grep -r "return_projector\|signal_analyzer" dashboard crypto-volatility-bot --include=*.py`로 다른 사용처가 없을 때만
- Test: `dashboard/tests/test_legacy_sim_removal.py`(추가), `dashboard/tests/test_sim_routes_kept.py`(신규)

**Interfaces:**
- Consumes: Task 1 스키마
- Produces: `main._register_jobs`에 `settle_predictions`·`sim_funding` id가 없음

- [ ] **Step 1: 테스트 추가**

```python
# test_legacy_sim_removal.py
@pytest.mark.parametrize("method,path", [("get","/api/sim/accounts"),("get","/api/sim/predictions"),
    ("get","/api/sim/scorecard"),("get","/api/sim/signals"),("get","/api/sim/macro-context"),
    ("get","/api/sim/projection"),("get","/api/sim/win-rate-analysis")])
def test_legacy_endpoints_404(method, path):
    from dashboard.backend.api.sim_routes import router
    app = FastAPI(); app.include_router(router, prefix="/api")
    assert getattr(TestClient(app), method)(path).status_code == 404

def test_legacy_jobs_not_registered():   # 기존 test_putcall.py의 DummyDispatcher 패턴 그대로
    from dashboard.backend import main
    scheduler = AsyncIOScheduler(timezone="UTC")
    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())
    assert scheduler.get_job("settle_predictions") is None
    assert scheduler.get_job("sim_funding") is None

# test_sim_routes_kept.py
def test_kept_routes_registered():
    from dashboard.backend.api.sim_routes import router
    paths = {r.path for r in router.routes}
    assert {"/sim/auto-backtest","/sim/composite-backtest","/sim/tune","/sim/tune/{job_id}",
            "/sim/leaderboard","/sim/leaderboard/{indicator}","/sim/leaderboard/reset"} <= paths

def test_leaderboard_ok(state_db):   # 임시 DB, 빈 리더보드도 200
    ...
    assert client.get("/api/sim/leaderboard").status_code == 200
```

- [ ] **Step 2: 실패 확인** — `.venv/Scripts/python.exe -m pytest dashboard/tests/test_legacy_sim_removal.py dashboard/tests/test_sim_routes_kept.py -q -p no:cacheprovider` → 404 테스트·잡 테스트 FAIL
- [ ] **Step 3: 삭제·정리** — 위 Files대로 지우고, 지운 뒤 생긴 미사용 import만 정리(`ruff check dashboard/backend --select F401`)
- [ ] **Step 4: 통과 확인** — 위 두 파일 PASS + `.venv/Scripts/python.exe -m pytest dashboard/tests -q -p no:cacheprovider` 전체 PASS(기준선 대비 새 실패 0) + `test_paper_engine.py` PASS
- [ ] **Step 5: 커밋** — `git commit -m "refactor: 수동 모의투자 API·잡·채점 코드 제거(백테스트·튜닝·리더보드 유지)"`

### Task 3: 바이낸스 현물 수집기

**Files:**
- Create: `dashboard/backend/collectors/binance_spot.py`
- Test: `dashboard/tests/test_learning_binance.py`

**Interfaces:**
- Produces: `BASE = "https://api.binance.com"`, `INTERVAL_MS = {"1d": 86_400_000, "4h": 14_400_000}`
- Produces: `async def fetch_symbol_info(symbol: str) -> dict | None` — `/api/v3/exchangeInfo?symbol=`. `status=="TRADING"`이고 `quoteAsset=="USDT"`면 `{"symbol","base_asset"}`, 아니면 None(400 응답 포함)
- Produces: `async def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int | None = None, now_ms: int | None = None) -> list[dict]` — 1000개씩 `startTime` 전진 페이지네이션, 각 봉 `{"open_time","open","high","low","close","volume"}`(float), `close_time >= now_ms`인 봉 제외
- Produces: `async def fetch_spot_price(symbol: str) -> float | None` — `/api/v3/ticker/price`
- Produces: `def save_candles(symbol: str, interval: str, bars: list[dict]) -> int` — `INSERT ... ON CONFLICT DO UPDATE`, 반환은 처리 행 수
- Produces: `def last_open_time(symbol: str, interval: str) -> int | None`
- HTTP: 모듈 전역 `httpx.AsyncClient(timeout=10)` 지연 생성(`bybit_ohlcv.py`의 `_get_client` 패턴). 테스트는 `httpx.MockTransport`로 클라이언트 교체

- [ ] **Step 1: 테스트 작성**

```python
async def test_klines_paginate_and_drop_open_bar(monkeypatch): # 2500개를 3페이지로, 마지막 1개는 미마감
    ...
    bars = await fetch_klines("BTCUSDT", "4h", start_ms=0, now_ms=NOW)
    assert len(bars) == 2499 and calls == 3
    assert all(b["open_time"] + INTERVAL_MS["4h"] <= NOW for b in bars)

def test_save_candles_idempotent(state_db):
    assert save_candles("BTCUSDT","1d",BARS) == len(BARS)
    save_candles("BTCUSDT","1d",BARS)
    assert count_rows("learning_candles") == len(BARS)

async def test_symbol_info_rejects_non_usdt_and_unknown(monkeypatch):
    assert await fetch_symbol_info("ETHBTC") is None      # quoteAsset BTC
    assert await fetch_symbol_info("NOPEUSDT") is None    # 400 응답
    assert (await fetch_symbol_info("SOLUSDT"))["base_asset"] == "SOL"
```

- [ ] **Step 2: 실패 확인** — `... test_learning_binance.py` → ImportError
- [ ] **Step 3: 구현** — 위 시그니처대로. 페이지네이션: 받은 마지막 `open_time + interval`을 다음 `startTime`으로, 응답이 1000개 미만이면 종료
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 바이낸스 현물 캔들·시세 수집기 추가"`

### Task 4: 학습 설정·추적 종목 관리 + 백필 (AC1)

**Files:**
- Create: `dashboard/backend/services/learning_settings.py`
- Create: `dashboard/backend/services/learning_symbols.py`
- Create: `dashboard/backend/api/learning_routes.py` (이 Task에서 symbols·settings 엔드포인트만)
- Modify: `dashboard/backend/main.py` (`_mount_dashboard_routers`에 `learning_router` 인증 포함 등록)
- Test: `dashboard/tests/test_learning_symbols.py`

**Interfaces:**
- Consumes: Task 3 `fetch_symbol_info`, `fetch_klines`, `save_candles`
- Produces: `class LearningError(ValueError)` (in `learning_settings.py`, 다른 learning 모듈이 import)
- Produces: `DEFAULTS = {"wyckoff": {"n":30,"width_pct":15.0,"vol_mult":2.0}, "elliott": {"threshold_1d":10.0,"threshold_4h":5.0,"levels":[0.382,0.5,0.618,1.0,1.618]}, "dca": {"symbol":"BTCUSDT"}}`; `def get_settings() -> dict`; `def update_settings(patch: dict) -> dict` — 범위 검증: n 5~200, width_pct 1~100, vol_mult 1~10, threshold 1~50, levels 1~10개 양수, dca.symbol은 추적 중인 종목. 위반 시 `LearningError`
- Produces: `MAX_SYMBOLS = 5`; `def list_symbols() -> list[dict]`; `def add_symbol(symbol: str) -> dict`(DB에 `backfill_status='pending'`로 넣기만, 6번째면 LearningError); `def remove_symbol(symbol: str) -> None`(열린 포지션 있으면 LearningError); `async def backfill_symbol(symbol: str) -> dict` — 두 interval을 `start_ms=0`부터 받아 저장, `listed_at`=첫 1d 봉 날짜, 상태 `done|failed`
- Produces(API, prefix `/api`): `GET /learning/symbols`, `POST /learning/symbols {"symbol"}` → `fetch_symbol_info` None이면 400, 아니면 `add_symbol` 후 `BackgroundTasks`로 `backfill_symbol` → 202, `DELETE /learning/symbols/{symbol}`, `GET /learning/settings`, `PUT /learning/settings`. `LearningError` → 400 `{"detail": 메시지}`

- [ ] **Step 1: 테스트 작성**

```python
def test_add_up_to_five_then_reject(client_with_db, mock_binance):  # mock_binance: 모든 *USDT 존재
    for s in ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT"]:
        assert client.post("/api/learning/symbols", json={"symbol": s}).status_code == 202
    r = client.post("/api/learning/symbols", json={"symbol": "ADAUSDT"})
    assert r.status_code == 400 and "5" in r.json()["detail"]

def test_unknown_pair_rejected(client_with_db, mock_binance):
    assert client.post("/api/learning/symbols", json={"symbol": "NOPEUSDT"}).status_code == 400

async def test_backfill_from_listing(state_db, mock_binance_history):  # 1d 3000봉, 4h 18000봉, 2017-08-17 시작
    res = await backfill_symbol("BTCUSDT")
    assert res["status"] == "done" and list_symbols()[0]["listed_at"] == "2017-08-17"
    assert count_rows("learning_candles", interval="1d") == 3000

def test_remove_with_open_position_rejected(state_db): ...   # Review Focus 5
def test_settings_validation(state_db):
    with pytest.raises(LearningError): update_settings({"wyckoff": {"n": 2}})
    with pytest.raises(LearningError): update_settings({"dca": {"symbol": "ETHUSDT"}})  # 미추적
```

- [ ] **Step 2: 실패 확인** → ImportError/404
- [ ] **Step 3: 구현** — 위 Interfaces. 설정은 `learning_settings` 테이블에 key별 JSON, 기본값과 깊은 병합
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 추적 종목·설정 관리와 상장일 백필 추가"`

### Task 5: 일목균형표 전체 요소 (AC3)

**Files:**
- Create: `dashboard/backend/services/learning_indicators.py`
- Test: `dashboard/tests/test_learning_ichimoku.py`

**Interfaces:**
- Produces: `def ichimoku(candles: list[dict], interval_ms: int, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, shift: int = 26) -> list[dict]` — 반환은 시간순 `{"time": open_time_ms, "tenkan", "kijun", "senkou_a", "senkou_b", "chikou"}`(값 없으면 None). 마지막 봉 뒤로 `shift`개의 미래 시각(`last + k*interval_ms`)을 덧붙여 선행스팬만 채운다. 선행스팬은 `shift`봉 앞으로, 후행스팬(종가)은 `shift`봉 뒤로 민 값
- Produces: `def ichimoku_state(candles: list[dict], ich: list[dict]) -> dict` — 마지막 마감 봉 기준 `{"cloud_position","tk_cross","chikou","future_cloud"}` (값 집합은 Global Constraints)

- [ ] **Step 1: 테스트 작성** (고가=저가=종가=i인 선형 캔들 100개로 손계산 값 고정)

```python
def test_ichimoku_linear():
    c = [{"open_time": i*DAY, "high": i, "low": i, "close": i, "open": i, "volume": 1} for i in range(100)]
    ich = ichimoku(c, DAY)
    row = {r["time"]: r for r in ich}
    assert row[60*DAY]["tenkan"] == 56.0        # (60+52)/2
    assert row[60*DAY]["kijun"] == 47.5         # (60+35)/2
    assert row[86*DAY]["senkou_a"] == (56.0+47.5)/2   # 60번 봉 값이 26봉 앞으로
    assert row[86*DAY]["senkou_b"] == (60+9)/2        # 52봉 고저 중간
    assert row[34*DAY]["chikou"] == 60                # 60번 종가가 26봉 뒤로
    assert len(ich) == 100 + 26 and ich[-1]["time"] == 125*DAY and ich[-1]["tenkan"] is None

def test_state_above_cloud_golden():
    st = ichimoku_state(c, ichimoku(c, DAY))
    assert st == {"cloud_position":"above","tk_cross":"golden","chikou":"above","future_cloud":"bullish"}
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현** — 위 시그니처. `numpy` 사용 가능(기존 의존성)
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 일목균형표 전체 요소 계산 추가"`

### Task 6: 와이코프 후보 (AC4)

**Files:**
- Modify: `dashboard/backend/services/learning_indicators.py`
- Test: `dashboard/tests/test_learning_wyckoff.py`

**Interfaces:**
- Produces: `def wyckoff_candidates(candles: list[dict], n: int = 30, width_pct: float = 15.0, vol_mult: float = 2.0, vol_lookback: int = 20) -> dict` → `{"volume_spikes": [time...], "candidates": [{"time","type":"spring|upthrust","strong": bool,"box_high","box_low"}], "current_box": {"high","low","start","end"} | None}`

판정 규칙(봉 i, i ≥ n):
```
box = candles[i-n:i]; hi = max(high); lo = min(low); avg = mean(close)
in_range = (hi - lo) / avg * 100 <= width_pct
spike(i) = i >= vol_lookback and vol[i] >= vol_mult * mean(vol[i-vol_lookback:i])
spring   = in_range and low[i]  < lo and lo <= close[i] <= hi
upthrust = in_range and high[i] > hi and lo <= close[i] <= hi
strong   = spike(i)
current_box = 마지막 봉 기준 박스가 in_range일 때만
```

- [ ] **Step 1: 테스트 작성** — 30봉 박스(100~110) 뒤에 ① 저가 95·종가 105 봉(거래량 평균의 3배) → spring strong ② 고가 115·종가 108 봉(거래량 평균) → upthrust not strong ③ 저가 95·종가 94 봉 → 후보 아님 ④ 폭 30% 박스 → 후보 0개 ⑤ `width_pct=40`으로 재계산하면 ④에서 후보 생김 ⑥ `vol_mult=4`면 ①이 strong 아님
- [ ] **Step 2: 실패 확인** → AttributeError
- [ ] **Step 3: 구현** — 위 규칙 그대로
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 와이코프 박스권·스프링·업스러스트 후보 판정 추가"`

### Task 7: 엘리엇 지그재그 피벗 + 피보나치 (AC5)

**Files:**
- Modify: `dashboard/backend/services/learning_indicators.py`
- Test: `dashboard/tests/test_learning_elliott.py`

**Interfaces:**
- Produces: `def zigzag(candles: list[dict], threshold_pct: float) -> list[dict]` → 확정 피벗 `[{"time","price","kind":"high|low"}]`(고가·저가 기준, 고/저 교대). 파동 번호 필드 없음
- Produces: `def fib_levels(pivots: list[dict], levels: list[float]) -> list[dict]` → 마지막 두 피벗 A(이전)·B(최근)로 `price = B.price + (A.price - B.price) * level`, `[{"level","price"}]`. 피벗 2개 미만이면 `[]`

지그재그(확정 규칙):
```
극값 후보 ext = 0번 봉, 방향 dir = None
각 봉 i:
  dir가 None: high[i]가 low[ext]보다 th% 이상 높으면 ext(저가)를 low 피벗 확정, dir='up', ext=i
              low[i]가 high[ext]보다 th% 이상 낮으면 ext(고가)를 high 피벗 확정, dir='down', ext=i
              (None 상태에선 ext를 최고가 봉/최저가 봉 두 개로 따로 추적)
  dir=='up':  high[i] >= high[ext]면 ext=i
              low[i] <= high[ext]*(1-th/100)면 ext를 high 피벗 확정, dir='down', ext=i
  dir=='down': 대칭
마지막 미확정 극값은 피벗으로 내보내지 않는다
```

- [ ] **Step 1: 테스트 작성** — 100→120→108→130 경로, threshold 10%: 확정 피벗은 `[(low,100), (high,120), (low,108)]` (120→108이 정확히 10% 되돌림이라 120 확정, 108→118.8 이상 상승에서 108 확정, 130은 미확정이라 제외). 같은 경로에 116→113 작은 되돌림(약 2.6%)을 넣고 threshold 2%로 다시 계산하면 116·113이 피벗에 추가됨. `fib_levels`: A=100(low), B=120(high)일 때 0.382→112.36, 0.5→110, 0.618→107.64, 1.0→100, 1.618→87.64 (`pytest.approx`). 결과 dict에 `wave` 키가 없음
- [ ] **Step 2: 실패 확인** → AttributeError
- [ ] **Step 3: 구현** — 위 규칙
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 엘리엇 학습용 지그재그 피벗·피보나치 레벨 추가"`

### Task 8: 차트·주문 컨텍스트 API

**Files:**
- Modify: `dashboard/backend/api/learning_routes.py`
- Test: `dashboard/tests/test_learning_chart_api.py`

**Interfaces:**
- Consumes: Task 4 `get_settings`, Task 5~7 함수, `learning_candles`
- Produces: `GET /learning/chart?symbol=&interval=1d|4h&limit=500` → `{"candles":[...], "ichimoku":[...], "wyckoff":{...}, "pivots":[...], "fib":[...], "state":{...}, "settings":{...}}`. 지표는 limit보다 52봉 더 읽어 계산 후 잘라 반환. 미추적 종목 404, 잘못된 interval 422
- Produces: `GET /learning/order-context?symbol=&interval=1d` → `{"ichimoku_state": {...}, "wyckoff_recent": [최근 5봉 안의 후보], "current_box": {...}|None}` (근거 입력 미리 채우기용)

- [ ] **Step 1: 테스트 작성** — 캔들 120개 넣고 `/api/learning/chart` 200, 키 7개 존재, `len(candles) <= limit`, 설정 `wyckoff.width_pct` 변경 후 결과 달라짐, 미추적 404, `interval=1h` 422. order-context가 `ichimoku_state`의 4개 키를 모두 가짐
- [ ] **Step 2~4:** 실패 확인 → 구현 → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 차트·주문 컨텍스트 API 추가"`

### Task 9: 온체인 수집·스케줄·실패 알림 + 체결 스냅샷 (AC2, AC8)

**Files:**
- Create: `dashboard/backend/collectors/learning_onchain.py`
- Create: `dashboard/backend/jobs/learning_collect.py`
- Create: `dashboard/backend/services/learning_snapshot.py`
- Modify: `dashboard/backend/main.py` (`_register_jobs`에 잡 3개)
- Test: `dashboard/tests/test_learning_collect.py`, `dashboard/tests/test_learning_snapshot.py`

**Interfaces:**
- Produces(collector, 각 함수는 `list[dict]` 행 `{"metric","scope","as_of","value","source"}` 반환, 실패는 예외):
  - `fetch_coinmetrics_btc()` → `mvrv`, `active_addresses`, `nupl`, `realized_price` (scope `BTC`, source `coinmetrics`). 요청 metrics `CapMVRVCur,AdrActCnt,PriceUSD`. `derive_nupl_realized(mvrv, price) -> (1 - 1/mvrv, price / mvrv)` 순수 함수
  - `fetch_mempool()` → `fee_fastest`(`/api/v1/fees/recommended`), `mempool_tx_count`(`/api/mempool`), `hashrate`(`/api/v1/mining/hashrate/3d` 최신) (scope `BTC`, source `mempool.space`)
  - `fetch_defillama()` → `stablecoin_supply`(scope `GLOBAL`), `sol_tvl`(scope `SOL`, `/v2/historicalChainTvl/Solana` 최신) (source `defillama`)
  - `fetch_binance_futures(symbol)` → `funding_rate`(`/fapi/v1/premiumIndex` lastFundingRate), `open_interest`(`/fapi/v1/openInterest`) (scope = symbol, source `binance-futures`). 선물 없는 종목은 빈 리스트 + `skipped`
  - `fetch_bgeometrics_sopr()` → `sopr` (scope `BTC`, source `bgeometrics`). 엔드포인트는 구현 시 무료 문서로 확인. 무료로 못 쓰면 멈추고 사용자에게 보고(Exit condition)
  - `fetch_fred_liquidity()` → `tga`, `m2` (scope `US`, source `fred`, 기존 `collectors/fred.fetch_tga/fetch_m2` 재사용)
- Produces(job):
  - `async def collect_learning_daily() -> None` — 1d 캔들(추적 종목, `last_open_time` 이후) + 위 소스 전부. 소스별로 `learning_collection_runs`에 `ok|failed|rate_limited|skipped`와 사유 기록, 실패는 `await notify_job_failure(f"learning:{source}", reason)`
  - `async def retry_learning_daily() -> None` — 오늘(UTC) 실패했거나 `coinmetrics` 최신 `as_of` < 어제인 소스만 재시도(`is_retry=1`)
  - `async def collect_learning_4h() -> None`
  - `def bgeometrics_budget_ok(now: datetime) -> bool` — 최근 1시간 bgeometrics 실행 < 8, 24시간 < 15
  - 스케줄: `CronTrigger(hour=0, minute=10, timezone="UTC")` id `learning_daily`, `CronTrigger(hour=4, minute=0, timezone="UTC")` id `learning_daily_retry`, `CronTrigger(hour="0,4,8,12,16,20", minute=5, timezone="UTC")` id `learning_4h`
- Produces(snapshot): `SNAPSHOT_METRICS`(BTC 맥락: mvrv, active_addresses, nupl, realized_price, sopr, fee_fastest, mempool_tx_count, hashrate / GLOBAL: stablecoin_supply / US: tga, m2 / 종목: funding_rate, open_interest / SOL 계열만: sol_tvl); `def build_snapshot(symbol: str) -> dict` → `{"symbol", "items": {metric: {"value","as_of","source"} | {"value": None, "reason": str}}}` — DB 최신값만 읽음(실시간 호출 없음), 없는 값의 reason은 해당 source 최근 실패 사유 또는 `"수집된 값 없음"`

- [ ] **Step 1: 테스트 작성**

```python
def test_jobs_scheduled():   # test_putcall.py 패턴: 실제 AsyncIOScheduler + get_job
    scheduler = AsyncIOScheduler(timezone="UTC")
    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())
    assert str(scheduler.get_job("learning_daily").trigger) == "cron[hour='0', minute='10']"
    assert str(scheduler.get_job("learning_daily_retry").trigger) == "cron[hour='4', minute='0']"
    assert str(scheduler.get_job("learning_4h").trigger) == "cron[hour='0,4,8,12,16,20', minute='5']"

async def test_source_failure_recorded_and_alerted(state_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET-TOKEN-123")
    sent = []; monkeypatch.setattr(jobs, "notify_job_failure", lambda j, e: sent.append((j, e)) or _noop())
    monkeypatch.setattr(onchain, "fetch_coinmetrics_btc", _raise(httpx.HTTPStatusError(...429...)))
    await collect_learning_daily()
    assert ("learning:coinmetrics" in [j for j, _ in sent])
    assert all("SECRET-TOKEN-123" not in e for _, e in sent)
    assert last_run("coinmetrics")["status"] == "failed"

def test_bgeometrics_budget(state_db): ...   # 15회 기록 후 False, 실행하면 rate_limited 기록·HTTP 호출 0
async def test_retry_only_stale_sources(state_db, ...): ...
def test_nupl_realized(): assert derive_nupl_realized(2.0, 60000.0) == (0.5, 30000.0)

# test_learning_snapshot.py
def test_snapshot_non_btc_includes_btc_context(state_db):
    seed_metrics(...)  # BTC mvrv, SOLUSDT funding_rate, SOL sol_tvl
    snap = build_snapshot("SOLUSDT")
    assert snap["items"]["mvrv"]["source"] == "coinmetrics" and snap["items"]["mvrv"]["as_of"] == "2026-11-17"
    assert snap["items"]["funding_rate"]["value"] == 0.0001 and "sol_tvl" in snap["items"]
    assert snap["items"]["sopr"]["value"] is None and snap["items"]["sopr"]["reason"]
    assert "sol_tvl" not in build_snapshot("ETHUSDT")["items"]

```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현** — 위 Interfaces. 소스 호출은 서로 독립(`asyncio.gather(..., return_exceptions=True)`), 예외 메시지는 `f"{type(e).__name__}: HTTP {status}"` 수준으로만 남겨 URL·헤더를 담지 않는다
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 온체인 수집 잡과 체결 스냅샷 추가"`

### Task 10: 모의 계좌·주문·근거 필수 (AC6, AC7)

**Files:**
- Create: `dashboard/backend/services/learning_account.py`
- Modify: `dashboard/backend/api/learning_routes.py`
- Test: `dashboard/tests/test_learning_trading.py`, `dashboard/tests/test_learning_rationale.py`

**Interfaces:**
- Consumes: `LearningError`, Task 3 `fetch_spot_price`, Task 9 `build_snapshot`
- Produces: `INITIAL_USDT = 10_000.0`, `FEE_RATE = 0.001`, `QTY_EPS = 1e-9`, `PHASES = {"accumulation","markup","distribution","markdown","unclear"}`
- Produces: `def validate_rationale(r: dict) -> dict` — `phase` 필수(PHASES), `ichimoku` 필수 4키(Global Constraints 값), `memo` 선택(문자열, 최대 2000자). 위반 시 LearningError
- Produces: `def get_account() -> dict` — 없으면 `started_at=now(UTC)`, cash 10000으로 생성
- Produces: `def place_order(symbol: str, side: str, price: float, rationale: dict, snapshot: dict, *, usdt_amount: float | None = None, qty: float | None = None, detected: dict | None = None, executed_at: str | None = None) -> dict`
  - buy: `usdt_amount` 필수·>0·≤cash, `fee = usdt_amount*FEE_RATE`, `qty = (usdt_amount-fee)/price`, cash -= usdt_amount. 열린 포지션 없으면 새 포지션(`first_entry_price=price`, `entry_phase=rationale.phase`)
  - sell: `qty` 필수·>0·≤보유(+QTY_EPS), `proceeds = qty*price`, `fee = proceeds*FEE_RATE`, cash += proceeds-fee. 남은 수량 < QTY_EPS면 0으로 맞추고 포지션 `closed`
  - 반환 `{"fill_id","position_id","qty","price","fee_usdt","cash_usdt"}`
- Produces: `def holdings(prices: dict[str, float], usd_krw: float | None) -> dict` → `{"cash_usdt","positions":[{"symbol","qty","avg_cost","market_value","unrealized_pnl"}],"equity_usdt","equity_krw"}` (rate None이면 krw None)
- Produces(API): `GET /learning/account`, `POST /learning/orders {"symbol","side","usdt_amount"|"qty","rationale":{...},"interval"}` — 서버가 `fetch_spot_price`로 체결가, `order-context`로 `detected` 기록, `build_snapshot`으로 스냅샷. 시세 조회 실패 시 503

- [ ] **Step 1: 테스트 작성**

```python
def test_buy_sell_fee_math(state_db):
    place_order("BTCUSDT","buy",50000.0,R,{},usdt_amount=1000.0)
    a = get_account(); assert a["cash_usdt"] == pytest.approx(9000.0)
    pos = holdings({"BTCUSDT":50000.0}, 1400.0)["positions"][0]
    assert pos["qty"] == pytest.approx(999.0/50000.0)
    place_order("BTCUSDT","sell",55000.0,R,{},qty=pos["qty"])          # 전량 매도
    assert get_account()["cash_usdt"] == pytest.approx(9000 + 999/50000*55000*0.999)
    assert open_positions() == []                                     # Review Focus 3

def test_overspend_and_oversell_rejected(state_db): ...  # cash 초과 buy, 보유 초과 sell → LearningError
def test_krw_shown(state_db): assert holdings({}, 1400.0)["equity_krw"] == pytest.approx(10000*1400)

# test_learning_rationale.py
@pytest.mark.parametrize("bad", [{}, {"phase":"moon"}, {"phase":"markup"},             # ichimoku 누락
    {"phase":"markup","ichimoku":{"cloud_position":"above"}}])                         # 키 부족
def test_rationale_required_for_buy_and_sell(bad, client): ...  # buy·sell 둘 다 400
def test_memo_optional(client): ...                             # memo 없이 201
def test_order_context_prefill(client): ...                     # order-context가 state·후보를 줌, 체결 fill에 detected_json 저장
def test_order_succeeds_with_empty_snapshot(client): ...       # 모든 수집원 실패 상태에서도 주문 201, fill.snapshot_json에 사유 저장
```

- [ ] **Step 2~4:** 실패 확인 → 구현 → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 모의 계좌·현물 주문·근거 필수 검증 추가"`

### Task 11: 일지·복기·국면 자동 판정 (AC9, AC10)

**Files:**
- Create: `dashboard/backend/services/learning_review.py`
- Modify: `dashboard/backend/api/learning_routes.py`
- Test: `dashboard/tests/test_learning_review.py`, `dashboard/tests/test_learning_phase_judgement.py`

**Interfaces:**
- Consumes: `learning_positions`, `learning_fills`, `learning_candles`(1d)
- Produces: `HORIZONS = (14, 28)`, `JUDGE_PCT = 5.0`
- Produces: `def judge_phase(phase: str, entry_price: float, close_price: float, pct: float = JUDGE_PCT) -> str | None` — accumulation·markup: `ret >= +pct` → `hit`, `ret <= -pct` → `miss`, 그 사이 `partial`; distribution·markdown은 부호 반대; unclear → None. `ret = (close/entry - 1)*100`
- Produces: `def journal(limit: int = 50) -> list[dict]` — 포지션별 `{"position","fills":[근거·스냅샷 포함]}`
- Produces: `def review_position(position_id: int, horizon_days: int, today: date | None = None) -> dict` — 기준일 = 첫 진입 UTC 날짜 + horizon. 기준일 > today 또는 그날 1d 캔들 없음 → `{"status":"pending","due": "YYYY-MM-DD"}`. 아니면 `{"status":"ready","rationale","close_price","pnl_usdt"(그날 종가 기준 실현+평가),"hold_return_pct","suggested","confirmed","reason"}` 반환하고 `learning_reviews.suggested` UPSERT
- Produces: `def confirm_review(position_id: int, horizon_days: int, verdict: str, reason: str) -> dict` — verdict `hit|partial|miss`, reason 필수(1~1000자)
- Produces(API): `GET /learning/journal`, `GET /learning/reviews/{position_id}`(14·28 둘 다), `POST /learning/reviews/{position_id}/{horizon_days}/confirm`

- [ ] **Step 1: 테스트 작성**

```python
@pytest.mark.parametrize("phase,close,expected", [
    ("markup",105,"hit"),("markup",104.99,"partial"),("markup",95,"miss"),
    ("accumulation",95.01,"partial"),("distribution",95,"hit"),("markdown",105,"miss"),("unclear",130,None)])
def test_judge_phase(phase, close, expected): assert judge_phase(phase, 100.0, close) == expected

def test_review_pnl_and_hold_return(state_db):
    # 11/01 1000 USDT 매수 @100, 11/10 절반 매도 @110, 11/15 1d 종가 120
    r = review_position(pid, 14, today=date(2026,11,20))
    assert r["hold_return_pct"] == pytest.approx(20.0)
    assert r["pnl_usdt"] == pytest.approx(realized_half_at_110 + unrealized_half_at_120 - fees)
    assert r["suggested"] == "hit"

def test_review_pending_when_no_candle(state_db): ...  # Review Focus 4
def test_confirm_overrides_and_persists(state_db): ...  # suggested hit → confirmed miss + reason 저장
def test_journal_groups_fills_by_position(state_db): ...
```

- [ ] **Step 2~4:** 실패 확인 → 구현 → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 일지·포지션 복기·국면 자동 판정 추가"`

### Task 12: 성과 지표·DCA 기준선 (AC11, AC12)

**Files:**
- Create: `dashboard/backend/services/learning_metrics.py`
- Modify: `dashboard/backend/api/learning_routes.py`
- Test: `dashboard/tests/test_learning_metrics.py`, `dashboard/tests/test_learning_dca.py`

**Interfaces:**
- Produces: `def hit_rate(horizon_days: int) -> dict` → `{"n","hit_rate","partial_ratio"}` — 대상은 `suggested IS NOT NULL`(불명확 제외)이고 `confirmed IS NOT NULL`인 행. `hit_rate = hit/n`, `partial_ratio = partial/n`, n=0이면 둘 다 None
- Produces: `def win_rate() -> dict` → `{"n","win_rate"}` — closed 포지션, 실현손익 = Σ매도(proceeds−fee) − Σ매수 usdt_amount > 0이면 승
- Produces: `def dca_baseline(start: date, until: date, closes: dict[date, float], initial: float = 10_000.0, weeks: int = 52, fee: float = 0.001) -> list[dict]` — 순수 함수. 매수일 = start + 7k (k=0..51, ≤ until), 회당 `initial/weeks`, 그날 종가 없으면 다음 종가 있는 날에 매수. 날짜별 `{"date","value"}` = 현금 + 보유수량×종가
- Produces: `def account_equity_series(start: date, until: date) -> list[dict]` — 날짜별로 그날까지의 체결을 반영하고 종목별 1d 종가로 평가
- Produces(API): `GET /learning/performance` → `{"hit_rate":{"14":...,"28":...},"win_rate":...,"equity":[...],"dca":{"symbol","series":[...]}|null,"dca_reason":str|null,"usd_krw"}` — 기준 종목 캔들 없으면 `dca: null`, `dca_reason="기준 종목(BTCUSDT) 캔들이 없습니다. 추적 목록에 추가하세요"` (Review Focus 5)

- [ ] **Step 1: 테스트 작성**

```python
def test_hit_rate_excludes_unclear_counts_partial_separately(state_db):
    seed_reviews([("hit","hit"),("partial","partial"),("miss","miss"),(None,None),("hit",None)])  # (suggested, confirmed)
    assert hit_rate(14) == {"n":3,"hit_rate":pytest.approx(1/3),"partial_ratio":pytest.approx(1/3)}

def test_win_rate_closed_only(state_db): ...   # 청산 2(수익1·손실1) + 열린 1 → n=2, 0.5

def test_dca_52_weeks():
    start = date(2026,1,1); closes = {start + timedelta(d): 100.0 for d in range(400)}
    s = dca_baseline(start, start + timedelta(399), closes)
    assert s[0]["value"] == pytest.approx(10000 - 10000/52*0.001)          # 첫날 1회 매수
    last = s[-1]["value"]; assert last == pytest.approx(10000*0.999)       # 52회 후 전액 투입, 이후 매수 없음
def test_dca_skips_missing_close_to_next_day(): ...
def test_performance_dca_null_when_ref_untracked(client): ...
```

- [ ] **Step 2~4:** 실패 확인 → 구현 → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 적중률·승률·DCA 기준선 성과 지표 추가"`

### Task 13: 프론트 API 클라이언트·차트 데이터 변환

**Files:**
- Create: `dashboard/frontend/src/lib/learningApi.ts`
- Create: `dashboard/frontend/src/components/learning/learningChartData.ts`
- Create: `dashboard/frontend/tests/learningChartData.test.ts`
- Modify: `dashboard/frontend/package.json` (`test` 스크립트 끝에 `&& node --experimental-strip-types tests/learningChartData.test.ts`)

**Interfaces:**
- Consumes: Task 4·8·9·11·12 API 응답 형태
- Produces(`learningApi.ts`, 모두 `apiFetch` 사용): `getSymbols()`, `addSymbol(symbol)`, `removeSymbol(symbol)`, `getSettings()`, `putSettings(patch)`, `getChart(symbol, interval, limit?)`, `getOrderContext(symbol, interval)`, `getAccount()`, `postOrder(body)`, `getJournal()`, `getReviews(positionId)`, `confirmReview(positionId, horizon, verdict, reason)`, `getPerformance()` + 응답 타입 정의
- Produces(`learningChartData.ts`, 순수 함수): `toCandleSeries(candles) -> {time: UTCTimestamp(초), open, high, low, close}[]`, `toLineSeries(ich, key) -> {time, value}[]`(null 제외), `toCloudBands(ich) -> {time, top, bottom, bullish}[]`, `toWyckoffMarkers(wyckoff) -> SeriesMarker[]`(spring=아래 화살표, upthrust=위 화살표, strong이면 텍스트에 '강'), `toPivotLine(pivots)`, `formatUsdtKrw(usdt: number, rate: number | null) -> string`(예: `"1,234.56 USDT (≈ 1,728,384원)"`, rate null이면 USDT만)

- [ ] **Step 1: 테스트 작성** — ms→초 변환, null 값 제외, 구름 상단·하단과 bullish 판정(senkou_a > senkou_b), strong 후보 마커 텍스트, `formatUsdtKrw(1234.56, 1400)` 정확한 문자열, rate null 처리
- [ ] **Step 2: 실패 확인** — `cd dashboard/frontend && node --experimental-strip-types tests/learningChartData.test.ts` → 모듈 없음
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `npm test` 전체 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 프론트 API 클라이언트와 차트 데이터 변환 추가"`

### Task 14: 학습 탭 화면 + 백테스트 연결 + Simulator 제거 (AC15, AC16)

**Files:**
- Create: `dashboard/frontend/src/components/screens/Learning.tsx` (하위 탭: 차트·매매·일지·복기·성과·백테스트, 상단에 추적 종목 관리)
- Create: `dashboard/frontend/src/components/learning/LearningChart.tsx` (lightweight-charts: 캔들 + 전환/기준/후행 라인 + 선행스팬 두 라인과 구름(밴드) + 와이코프 마커 + 지그재그 라인 + 피보 가격선, 일봉/4시간봉 전환, 설정 패널)
- Create: `dashboard/frontend/src/components/learning/TradePanel.tsx` (order-context로 국면·일목 선택지 미리 채움, 근거 미입력 시 버튼 비활성, 매수 USDT 금액/매도 수량, 계좌·원화 환산 표시)
- Create: `dashboard/frontend/src/components/learning/JournalPanel.tsx`, `ReviewPanel.tsx`(14·28일, 실현+평가 vs 보유 가정, 제안 판정 + 확정/수정·이유 입력), `PerformancePanel.tsx`(적중률 14/28·부분 비율, 승률, 계좌 vs DCA 라인, DCA 기준 종목 선택), `BacktestPanel.tsx`(기존 `CompositeSimulator`·`AutoBacktest`를 그대로 렌더)
- Modify: `dashboard/frontend/src/App.tsx` — `TABS`에 `{ path: '/learning', label: '학습', description: '차트로 국면을 판단하고 근거와 함께 모의매매한 뒤 복기합니다.' }`, `<Route path="/learning" element={<Learning />} />`
- Delete: `dashboard/frontend/src/components/screens/Simulator.tsx`, `dashboard/frontend/src/components/shared/SimScorecard.tsx`

**Interfaces:**
- Consumes: Task 13 전부, 기존 `KrStockChart.tsx`의 lightweight-charts 생성·정리(useEffect cleanup) 패턴

- [ ] **Step 1: 빌드 기준 확인** — `cd dashboard/frontend && npm run build` 현재 PASS 확인
- [ ] **Step 2: 화면 구현** — 위 파일. 화면 문구 한국어, 국면 표기는 매집·상승·분산·하락·불명확
- [ ] **Step 3: 타입·빌드·단위 테스트** — `npm run lint`(새 경고 0), `npm test` PASS, `npm run build` PASS
- [ ] **Step 4: 브라우저 확인(로컬)** — 저장소 루트에서 임시 DB로 백엔드 실행: `DATABASE_PATH=<scratch>/learn.db TELEGRAM_BOT_TOKEN=x TELEGRAM_CHAT_ID=0 .venv/Scripts/python.exe -m uvicorn dashboard.backend.main:create_application --factory --port 8081`, 프론트 `VITE_API_URL=http://localhost:8081 npm run dev`. 확인: 기존 탭 10개 그대로 + '학습' 탭, BTCUSDT 추가 → 백필 후 차트에 일목·구름·와이코프 마커·지그재그·피보, 근거 없이 주문 불가, 근거 넣고 매수 → 계좌·원화 환산, 일지 표시, 백테스트 하위 화면에서 종합 백테스트 실행 결과 표시
- [ ] **Step 5: 커밋** — `git commit -m "feat: 학습 탭 화면 추가, 백테스트 화면 연결, Simulator 제거"`

### Task 15: 전체 검증과 문서 갱신

**Files:**
- Modify: `docs/plans/learning-tab-phase1-spec-2026-11-18.md` (구현 결과·남은 가정 갱신)
- Modify: `D:\Dev\coolify-migration\MEMORY.md` (학습 탭 배포 시 필요한 것: 첫 배포 때 sim 백업 파일 위치 `/app/data/backups/`)

- [ ] **Step 1:** `.venv/Scripts/python.exe -m pytest crypto-volatility-bot/tests dashboard/tests -q -p no:cacheprovider` → 전체 PASS(기준선 대비 새 실패 0)
- [ ] **Step 2:** `.venv/Scripts/python.exe -m ruff check crypto-volatility-bot/app dashboard/backend --select E,F,W --ignore E501` → 0
- [ ] **Step 3:** `cd dashboard/frontend && npm test && npm run build` → PASS
- [ ] **Step 4:** 수용 기준 16개를 스펙 3장 표 순서대로 대조해 각 기준의 증거(테스트 이름 또는 브라우저 확인)를 스펙 문서에 기록
- [ ] **Step 5: 커밋** — `git commit -m "docs: 학습 탭 1차 구현 결과와 검증 기록"` (push는 사용자 승인 후. push = Railway·OCI 자동 배포)
