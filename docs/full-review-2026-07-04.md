# 전체 검수 보고서 — 2026-07-04

범위: crypto-volatility-bot(봇) · dashboard 백엔드 · 프론트엔드 · 저장소/배포 위생.
방법: 영역별 검토 에이전트 4개 병렬 + 핵심 발견 교차 검증.
전제: **GitHub 저장소가 PUBLIC**임을 확인 — 보안 항목은 공개 저장소 기준 심각도.

표기: ✅ = 직접 코드로 확인함 / ⚠️ = 에이전트 보고, 정황 강함 / ❓ = 불확실(검증 필요)

---

## A. 보안·유출 (즉시 조치)

### A-1. DB 덤프 4종이 .gitignore에 없음 ✅ [높음]
`crypto_dump.sql`(100K) · `crypto_inserts.sql` · `ohlcv_inserts.sql` · `crypto_b64.txt`(crypto.db 자체의 base64).
`*.db`는 막혀 있지만 이 4개는 안 막혀 있어 `git add -A` 한 번이면 공개 저장소에 DB 내용(whale 워치리스트 등 운영 데이터) 유출.
2026-04-19 생성 — Railway DB 마이그레이션 일회성 산물로 추정.
→ **조치**: 삭제(사용자 확인 후) + `.gitignore`에 `*_dump.sql`, `*_inserts.sql`, `crypto_b64.txt`, `.mcp.json` 추가.

### A-2. SPA catch-all 경로 탐색(path traversal) 가능성 ✅ [높음]
[main.py:192-197](../dashboard/backend/main.py#L192) — `_FRONTEND_DIST / full_path`를 정규화 없이 `is_file()` 후 서빙. 이 라우트는 **무인증**. `../` 시퀀스가 라우팅을 통과하면 `.env`·`crypto.db`까지 노출 가능. Starlette/uvicorn의 URL 정규화가 어디까지 막는지는 ❓이지만 방어 비용이 낮으므로 무조건 수정.
→ **조치**: `candidate.resolve()` 후 `_FRONTEND_DIST` 하위인지 검증.

### A-3. 인증 시크릿 기본값 폴백 ✅ [높음]
- [auth.py:14-16](../dashboard/backend/middleware/auth.py#L14): `PIN_CODE` 기본 `"1234"`, `APP_SECRET` 기본 `"change-me-in-production"` — 공개 저장소라 env 미설정 시 토큰 위조·로그인 가능.
- 봇 [webhook_server.py:22-23](../crypto-volatility-bot/webhook_server.py#L22) ⚠️: `_check_admin`이 `ADMIN_KEY` **미설정 시 통과** → `/scheduled-run`·`/scheduled-report` 무인증 노출.
→ **조치**: 프로덕션에서 기본값/미설정이면 기동 실패(raise). Railway에 실제 값 설정됐는지 확인.

---

## B. 신뢰성 — 알림이 조용히 죽는 경로

### B-1. 봇 모듈 로그가 전부 유실 ⚠️ [높음]
[logger.py:17](../crypto-volatility-bot/app/utils/logger.py#L17) — `setup_logger("crypto-bot")`는 그 이름의 로거만 구성하는데 모든 모듈은 `logging.getLogger(__name__)`(`app.*`) 사용 → INFO 전부 유실, WARNING은 비정형 stderr. 이 봇의 실패 처리 철학이 "폴백+warning"인데 그 warning이 안 보임 — **다른 조용한 실패들이 몇 주씩 숨는 구조적 원인**.
→ **조치**: `setup_logger`가 `"app"` 로거(또는 루트)에 핸들러를 달도록 수정.

### B-2. 고래(WHALE) 알림은 죽은 기능 ⚠️ [높음]
[data_collector.py:125](../crypto-volatility-bot/app/data/data_collector.py#L125) — `dormant_whale_activated: False` 하드코딩 → `_check_whale` 도달 불가. 테스트는 주입 데이터로만 통과해 CI로 감지 안 됨.
→ **조치**: 실제 감지 구현하거나 알림 경로·포맷터에서 제거(TODO 명시).

### B-3. 알림 전송 실패 처리 묶음 ⚠️ [중간]
- 봇 [notification_dispatcher.py:189-217](../crypto-volatility-bot/app/notification_dispatcher.py#L189): `send_message()` 실패해도 쿨다운 설정 → 실패한 알림이 2~6시간 유실.
- 대시보드 [direction_watch.py](../dashboard/backend/jobs/direction_watch.py): 상태를 **발송 전에 커밋** → 발송 실패 시 방향 전환/TGA 이벤트 영구 유실(재알림 안 됨).
- 봇 에러 알림: 예외 문자열 HTML 미이스케이프(`parse_mode=HTML`) → 에러 알림 자체가 전송 실패 가능 + 쿨다운 없어 지속 장애 시 스팸.
→ **조치**: 발송 성공 후 쿨다운/상태 커밋, `html.escape()`, 에러용 쿨다운.

### B-4. SPF 판정 조용한 스킵 ⚠️ [중간]
collect_spf가 `price=None`으로 저장한 예측은 update_predictions에서 로그 없이 영구 미판정 → 적중률 통계 왜곡.
→ **조치**: 미판정 사유 로깅 + price 백필 또는 다음 실행에서 재시도.

### B-5. 레거시 봇 Dockerfile ✅ [낮음 — 정정]
봇 전용 [crypto-volatility-bot/Dockerfile](../crypto-volatility-bot/Dockerfile)은 dashboard 없이 빌드돼 쿨다운·이력이 전부 ImportError가 되지만, **실제 Railway 배포는 루트 Dockerfile**(봇+대시보드+PYTHONPATH 모두 포함)이라 현재는 영향 없음. 오해 방지를 위해 레거시 Dockerfile 삭제 또는 "standalone 실행 시 쿨다운 미동작" 주석 필요.

---

## C. 정확성 — 계산·데이터 정합

### C-1. paper_rebalance 멱등성 없음 ⚠️ [중간]
같은 날 재실행 시(재시작·수동 트리거) 펀딩·수수료 이중 차감, 델타 매매 중복 → capital 왜곡. `paper_equity`만 ON CONFLICT 멱등.
→ **조치**: 해당 날짜 `paper_equity` 스냅샷 존재 시 스킵.

### C-2. `_clamp(NaN)` = 100 ⚠️ [중간]
[base.py:23-24](../crypto-volatility-bot/app/analyzers/base.py#L23) — NaN이 min/max를 통과해 100 반환. OHLCV가 정확히 20행이면 변동성 지표가 NaN → 만점 기여 → 오탐.
→ **조치**: NaN이면 50 반환 또는 해당 지표 제외.

### C-3. BTC 기준 하드코딩 상수의 ETH 오적용 ⚠️ [중간]
`technical.yaml` ATR normalize min:100/max:5000(절대 USD) → ETH ATR은 항상 0으로 정규화 → **ETH 알림 체계적 억제**. 고래 임계·OI/FR 임계도 BTC 백테스트 기준 전 심볼 공용.
→ **조치**: ATR을 가격 대비 % 정규화로 전환 또는 심볼별 설정.

### C-4. async 잡의 이벤트 루프 블로킹 불일치 ⚠️ [중간]
paper_rebalance·settle_predictions는 async인데 DB 접근을 `asyncio.to_thread` 없이 수행(동기 Lock) → SQLite I/O 동안 이벤트 루프 정지. check_direction_and_health만 to_thread 사용 — 일관성 없음.
→ **조치**: DB 무거운 잡은 to_thread로 감싸기.

### C-5. settle_predictions가 만료 시점이 아닌 현재가로 채점 ⚠️ [중간]
크립토 최대 ~1시간, 주식은 주말 지연 시 며칠 오차.

### C-6. 기타 (낮음)
- DerivativesAnalyzer SHORT_CROWDED 분기 dead code (의도 확인 필요 ❓)
- rsi_extreme 쿨다운이 yaml 주석 의도와 반대 동작으로 보임 ❓
- RSI 워밍업 NaN을 100으로 fillna
- OI 데이터 2~3개일 때 3일 변화율 왜곡
- score_aggregator·technical.yaml 문서-코드 드리프트
- sim_engine `_fetch_funding_rate` 항상 0 (미구현 플레이스홀더)
- 분석기 4종을 심볼·사이클마다 재생성(YAML 재파싱)

---

## D. 프론트엔드 UX

### D-1. 전역 ErrorBoundary 부재 ⚠️ [높음]
null 필드 하나에 `.toFixed()` 호출이 터지면 **탭 전체 백지**. 방어 없는 지점 다수(Dashboard.tsx:544·199, SPF.tsx:270, Leaderboard.tsx:199 등).
→ **조치**: main.tsx에 ErrorBoundary 1개(메시지+새로고침) + 핵심 지점 `?? 0`/옵셔널 체이닝.

### D-2. 폴링 1회 실패 시 보던 화면이 통째로 에러 화면 ⚠️ [중간]
화면 7곳이 `if (error) return <ErrorState/>`를 data 보유보다 먼저 체크. 모바일 네트워크 전환 한 번에 대시보드 소실. 5xx는 재시도 대상도 아님.
→ **조치**: `if (error && !data)`로 변경 + data 있으면 "갱신 실패" 배너만.

### D-3. PIN 로그인 fetch만 `VITE_API_URL` 미적용 ⚠️ [중간]
App.tsx:40 상대경로 — 프론트·API 오리진이 다르면 로그인만 실패.

### D-4. 기타 (낮음)
- Simulator 탭: 숨겨진 수동예측 뷰용 API 6회 낭비 호출
- PIN 빠른 연타 시 자릿수 유실(비함수형 setState)
- TradingView 스크립트 로드 실패 시 무한 스피너
- 수동예측 뷰 재활성 시 고정폭 테이블 모바일 잘림(잠재)
- `frontend/.env`의 `VITE_PIN_CODE=0000` 잔재 삭제

---

## E. 저장소·배포 위생

- [중간] `requirements-lock.txt` 죽은 파일 — Dockerfile은 범위지정 requirements.txt 사용(비재현 빌드). lock 재생성해 사용하거나 삭제.
- [낮음] 루트 Dockerfile에 gcc/g++ 잔류(이미지 비대), `npm install`→`npm ci`, CI Python 3.11 vs 배포 3.12 불일치
- [낮음] 공개 저장소인데 루트 README 없음
- [낮음] 4월 초기 기획 문서(가이드1/2, 기획서.html 등) → `docs/archive/` 이동 권장
- [낮음] `.ouroboros_eval_artifact.md` 루트 방치 — docs/plans/ 이동 또는 삭제
- 시크릿 하드코딩: 추적 파일·전체 히스토리(232커밋) 패턴 스캔 매치 0건 (무패턴 키까지 전수 보장은 ❓)
- CI 존재(GitHub Actions: ruff+pytest+tsc) — 양호

---

## 권장 작업 순서

| 순서 | 작업 | 규모 |
|---|---|---|
| 1 | A-1 덤프 파일 정리 + .gitignore | 몇 분 |
| 2 | A-2 경로 탐색 방어 (resolve 검증 3줄) | 몇 분 |
| 3 | A-3 시크릿 기본값 제거 + Railway env 확인 | 30분 |
| 4 | B-1 봇 로거 수정 (관측성 확보 — 이후 문제를 보이게 함) | 30분 |
| 5 | D-1·D-2 ErrorBoundary + error&&!data | 1~2시간 |
| 6 | B-3 알림 전송 실패 처리 묶음 | 1~2시간 |
| 7 | C-1 리밸런스 멱등화 | 1시간 |
| 8 | B-2 고래 알림 결정(구현 or 제거) | 결정 필요 |
| 9 | C-3 ETH 상수 (ATR % 정규화) | 검증 포함 반나절 |
| 10 | 나머지 중간·낮음 항목 | 점진적 |
