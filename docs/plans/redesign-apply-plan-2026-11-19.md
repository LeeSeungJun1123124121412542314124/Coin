# 리디자인 적용 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프론트 11개 화면을 시안의 고급 다크 디자인(토큰·글꼴·그룹 메뉴·한국식 상승/하락 색)으로 바꾸고 시안 전용 기능 5개를 넣는다.

**Architecture:** 색·간격 값은 `index.css` `:root` CSS 변수 한 곳에 두고, 인라인 스타일은 `var(--토큰)` 문자열로 바꾼다. 캔버스·SVG 차트(lightweight-charts, recharts)가 쓰는 같은 값은 `src/lib/theme.ts`의 `C` 객체에서 가져오고, 두 곳 값이 같은지 테스트로 묶는다. 새 기능의 데이터 가공은 순수 함수 모듈로 빼서 node 테스트한다.

**Tech Stack:** React 19 + TypeScript + Vite, recharts, lightweight-charts 5, node 내장 test(`--experimental-strip-types`)

**Spec:** `docs/plans/redesign-apply-spec-2026-11-19.md` (시안: https://claude.ai/artifact/QXBYctLdHA5bNMyfbHs9Mr)

## Global Constraints
- 토큰 값은 스펙 3절 표 그대로(예: `--bg #09090B`, `--surface #131316`, `--accent #C8A86B`, `--up #F2606A`, `--down #5AA9FF`, `--warn #E8913A`, `--ok #3FCB8B`)
- 상승·롱·매수·급등·강세 = `--up`, 하락·숏·매도·급락·약세 = `--down`, 변화 표시에는 ▲/▼(또는 +/−)를 함께 붙인다
- 상승/하락이 아닌 뜻의 빨강·초록은 의미 토큰으로: 과열·주의·경계·하락위험 = `--warn`, 침체·정상·반등기대·공급·적중 = `--ok`, 위험·확인 경보 = `--danger`. RSI 70/30, 공포탐욕 75/25, Put/Call 0.7/1.0 기준선, 와이코프 스프링/업스러스트 마커, LEVEL 색이 여기에 해당
- 글꼴: `index.html`에 Google Fonts `<link>` (IBM Plex Sans KR 400;500;600;700, IBM Plex Mono 400;500;600). 숫자(가격·수량·비율·시각·점수)는 Mono
- 카드 = `var(--surface)` + `1px solid var(--border)` + radius 16px + `box-shadow: var(--shadow-card)` + 여백 18px 20px
- 새 npm 패키지 금지, 백엔드 변경 금지, 기존 데이터·조작·라우트 경로 유지
- 외과적 변경: 색·배치·글꼴과 스펙 5절 기능만. 로직 리팩터링 금지. 이번 변경으로 안 쓰이게 된 CSS 규칙만 지우고, 원래부터 안 쓰이던 규칙(`.app-topbar` 등)은 보고만
- 코드 주석·커밋 한국어, 커밋 `type: 한국어 설명`, 커밋은 master 로컬만(push 금지)
- 새 테스트 파일은 `package.json`의 `test` 스크립트 끝에 `&& node --experimental-strip-types tests/<이름>.test.ts`로 붙인다. 테스트가 import하는 모듈은 React·CSS import 없는 순수 TS, 타입은 `import type`

## 옛 색 → 토큰 기본 대응 (맥락이 다르면 의미 기준으로 판단)
| 옛 값 | 기본 토큰 |
|---|---|
| `#0f1117`(바탕) | `--bg` |
| `#0f172a` | `--bg-inset` |
| `#1e293b`(카드 바탕) | `--surface` |
| `#334155`(카드·입력 테두리) | `--border`(카드) / `--border-strong`(입력·배지) / `--seg-active`(막대 트랙) |
| `#e2e8f0` `#f1f5f9` `#f8fafc` | `--text` |
| `#cbd5e1` `#94a3b8` | `--text-2` |
| `#64748b` `#475569` | `--text-3`(글자) / `--line`(구분선·격자) |
| `#60a5fa` `#38bdf8`(선택·강조 UI) | `--accent` |
| `#60a5fa` `#38bdf8`(데이터 시리즈) | `C.info` 또는 `C.accent` |
| `#4ade80` `#22c55e` `#36c273`(상승 뜻) | `--up` |
| `#f87171` `#ef4444` `#ff5d51`(하락 뜻) | `--down` |
| `#f59e0b` `#f97316` `#fbbf24`(주의) | `--warn` |
| `#a78bfa` `#a855f7` | `--violet` |

## Review Focus
1. 상승/하락이 아닌 빨강·초록(RSI·공포탐욕·Put/Call 기준선, LEVEL 색, 와이코프 마커)이 `--up/--down`으로 잘못 바뀌면 뜻이 뒤집힌다 → Task 6·7·8 리뷰에서 파일별로 확인
2. 390px 폭에서 표가 화면 밖으로 밀리거나 하단 메뉴가 내용을 가리면 안 된다 → Task 2 CSS(본문 하단 여백), 표는 `.table-scroll` 유지
3. BTCUSDT를 추적하지 않거나(404) 응답이 비면 대시보드 국면 카드가 빈 상태 안내로 바뀌고 화면이 깨지지 않아야 한다 → Task 4 `summarizeBtcPhase` 테스트
4. 알림 날짜 묶음은 KST 기준이라 UTC 14:59와 15:00이 다른 날이 된다 → Task 8 `groupAlertsByDay` 테스트
5. CSS 토큰과 `theme.ts` 값이 어긋나면 차트만 다른 색이 된다 → Task 1 토큰 일치 테스트

---

### Task 1: 디자인 토큰·글꼴·공용 색 모듈

**Files:**
- Modify: `dashboard/frontend/index.html` (글꼴 link, `lang="ko"`)
- Modify: `dashboard/frontend/src/index.css` (맨 위 `:root` 토큰 블록, body 바탕·글꼴·글자색, `.mock-up`/`.mock-down`/`.mock-direction-up/-down` 색을 토큰으로)
- Modify: `dashboard/frontend/src/lib/theme.ts`
- Create test: `dashboard/frontend/tests/themeTokens.test.ts`

**Interfaces:**
- Produces: CSS 변수 `--bg --bg-inset --surface --surface-2 --border --line --seg-active --border-strong --text --text-2 --text-3 --accent --link --link-hover --up --down --warn --warn-text --ok --danger --violet --info --neutral-series --shadow-card --radius-card --font-sans --font-mono`
  - `--shadow-card: inset 0 1px 0 rgba(255,255,255,0.035), 0 8px 24px rgba(0,0,0,0.35)`, `--radius-card: 16px`, `--font-sans: 'IBM Plex Sans KR', system-ui, sans-serif`, `--font-mono: 'IBM Plex Mono', ui-monospace, monospace`
- Produces (`theme.ts`): `export const C = { bg, bgInset, surface, surface2, border, line, segActive, borderStrong, text, text2, text3, accent, up, down, warn, warnText, ok, danger, violet, info, neutralSeries }` (hex 문자열, CSS와 같은 값)
- Produces: `changeColor(v: number | null | undefined): string` — 양수 `C.up`, 음수 `C.down`, 0·null·NaN `C.text2`
- Produces: `changeArrow(v): '▲' | '▼' | '–'`, `softBg(hex: string, alpha: number): string` (`rgba(r,g,b,a)`)
- `LEVEL_COLORS` 등 기존 LEVEL 객체는 이름 유지, bullish → `C.up`, bearish → `C.down`, warning → `C.warn`, critical → `C.danger`, neutral → `C.text2`(배경·테두리도 같은 색의 투명값)

- [ ] **Step 1: 실패하는 테스트** `tests/themeTokens.test.ts`
  - `index.css`를 `fs`로 읽어 `:root` 블록의 `--bg`·`--surface`·`--accent`·`--up`·`--down`·`--warn`·`--ok` 등 `C`에 있는 모든 키의 값이 `C`와 같다(키 이름은 camelCase ↔ kebab-case 대응)
  - `changeColor(1.2) === C.up`, `changeColor(-0.1) === C.down`, `changeColor(0) === C.text2`, `changeColor(null) === C.text2`, `changeColor(NaN) === C.text2`
  - `changeArrow(3) === '▲'`, `changeArrow(-3) === '▼'`, `changeArrow(0) === '–'`
  - `softBg('#F2606A', 0.14) === 'rgba(242,96,106,0.14)'`
- [ ] **Step 2:** `npm test` → FAIL
- [ ] **Step 3:** 구현. `package.json` test 스크립트에 새 테스트 추가
- [ ] **Step 4:** `npm test`, `npm run build` PASS
- [ ] **Step 5:** 커밋 `feat: 디자인 토큰과 글꼴, 한국식 상승·하락 공용 색 추가`

### Task 2: 앱 셸 — 그룹 사이드바·페이지 머리·모바일 5칸 메뉴

**Files:**
- Create: `dashboard/frontend/src/lib/navGroups.ts`
- Modify: `dashboard/frontend/src/App.tsx` (TABS 설명·경로는 그대로, 렌더 구조만)
- Modify: `dashboard/frontend/src/index.css` (새 `.shell-*` 규칙, 이 변경으로 안 쓰이게 된 `.mock-sidebar*`·`.mock-top-ticker`·`.mock-header-*`·`.mock-brand*`·`.mock-bottom-*` 삭제)
- Create test: `dashboard/frontend/tests/navGroups.test.ts`

**Interfaces:**
- Produces (`navGroups.ts`): `NAV_GROUPS: { label: string; paths: string[] }[]` = 개요['/'], 시장['/market','/liquidity','/volume'], 파생 · 온체인['/spf','/cvd','/whale'], 기록 · 검증['/research','/leaderboard','/alerts'], 학습['/learning']
- Produces: `MOBILE_PRIMARY: { label: string; path: string }[]` = 홈 '/', 시장 '/market', 파생 '/spf', 학습 '/learning' (5번째 칸은 "더보기" 버튼)
- Produces: `groupOf(path: string): string` — 그 경로가 속한 그룹 label(페이지 머리 위치 표시에 씀)
- 레이아웃: 데스크톱 = 왼쪽 232px 사이드바(브랜드 + 그룹 label 11px/600/자간 .08em `--text-3` + 링크 40px, 아이콘 18px stroke) + 본문(`padding: 32px 40px 56px`). 페이지 머리 = `{그룹} / {탭}` 13px → 제목 30/700 → 설명 14 `--text-2`, 오른쪽에 "최종 갱신 HH:MM"(기존 `dashboard:last-updated` 이벤트 값)
- 768px 미만: 사이드바 숨김, 하단 고정 5칸 메뉴(높이 64px, 활성 `--accent`), 본문 하단 여백 = 메뉴 높이 + 16px. "더보기"는 `MOBILE_PRIMARY`에 없는 나머지 화면 링크를 그룹별로 보여 주는 시트(기존 `shared/Modal` 재사용 가능), 링크를 누르면 닫힘
- PIN 화면도 토큰 색으로(구조는 그대로)

- [ ] **Step 1: 실패하는 테스트** `tests/navGroups.test.ts`: `NAV_GROUPS`의 paths를 모두 합치면 11개이고 중복 없음, App의 11개 경로 목록(테스트 안에 상수로)과 같다 / `MOBILE_PRIMARY` 4개 경로가 모두 `NAV_GROUPS`에 있다 / `groupOf('/whale') === '파생 · 온체인'`, `groupOf('/') === '개요'`, `groupOf('/nope') === ''`
- [ ] **Step 2:** `npm test` → FAIL
- [ ] **Step 3:** 구현(테스트 스크립트 추가 포함)
- [ ] **Step 4:** `npm test`, `npm run build`, `npx eslint src/App.tsx src/lib/navGroups.ts` 통과
- [ ] **Step 5:** 커밋 `feat: 그룹 사이드바와 모바일 5칸 메뉴로 앱 셸 교체`

### Task 3: 공용 컴포넌트 토큰화

**Files (Modify, `dashboard/frontend/src/components/shared/`):** `Card.tsx`, `StatRow.tsx`, `ScoreBar.tsx`, `AssetTabs.tsx`, `LastUpdated.tsx`, `Skeleton.tsx`, `ErrorState.tsx`, `ErrorBoundary.tsx`, `GaugeChart.tsx`, `Modal.tsx`, `StockCard.tsx`, `StockIndexCard.tsx`, `GlobalMarketCard.tsx`, `StockIndexModal.tsx`, `MacroHealthCard.tsx`, `AltcoinSeasonCard.tsx`, `EconomicNewsSection.tsx`, 그리고 `index.css`의 `.dashboard-*`·`.grid-*`·`.table-scroll`·`.stock-card`·`.coin-card` 색

**Interfaces:**
- Consumes: Task 1 `C`, `changeColor`, `changeArrow`, `softBg`, CSS 변수
- `Card`: 카드 규격(Global Constraints). 제목이 있으면 15/600
- `AssetTabs`: 세그먼트 컨트롤(바탕 `--bg-inset` + 테두리 `--border` + 안쪽 3px, 선택 `--seg-active` + `--text` + 600, 높이 38px, role=tab·aria-selected). 기존 props·URL 동기화 동작은 그대로
- `StatRow`: 행 높이 44px, 위 구분선 `--line`, 라벨 14 `--text-2`, 값 Mono 15, 변화는 `changeColor`+`changeArrow`
- `ScoreBar`: 트랙 `--seg-active` 6~8px radius 999, 채움 색은 호출자가 준 의미 색(기본 `--accent`)
- `Skeleton`: `--surface` ↔ `--surface-2` shimmer
- 상승/하락 판정 삼항식(`isPositive ? '#4ade80' : '#f87171'` 류)은 `changeColor` 호출로
- 숫자 표시는 `font-family: var(--font-mono)`

- [ ] **Step 1:** 파일마다 색·글꼴·카드 규격을 토큰으로 바꾼다(위 대응표, 의미 판단 우선)
- [ ] **Step 2:** `npm test`, `npm run build`, 변경 파일 eslint 새 오류 없음
- [ ] **Step 3:** 커밋 `feat: 공용 카드·탭·행 컴포넌트를 새 디자인 토큰으로`

### Task 4: 대시보드 + BTC 시장 국면 카드

**Files:**
- Create: `dashboard/frontend/src/components/screens/dashboardPhase.ts`
- Modify: `dashboard/frontend/src/components/screens/Dashboard.tsx`, `index.css`의 대시보드용 `.mock-*`(content-grid, direction, gauge, main-chart, real-dashboard, card-edit-mark, empty 등) 색·카드
- Create test: `dashboard/frontend/tests/dashboardPhase.test.ts`

**Interfaces:**
- Consumes: `learningApi`의 차트 응답 타입(`ChartResponse`, 기존), `GET /api/learning/chart?symbol=BTCUSDT&interval=1d&limit=90`
- Produces: `summarizeBtcPhase(res: ChartResponse | null): BtcPhase | null` — `{ close, changePct, low, high, spark: string, states: { k: string; v: string; tone: 'up' | 'down' | 'flat' }[] }`. `spark`는 300×64 viewBox polyline points 문자열. 캔들이 2개 미만이면 `null`
  - states 라벨·값은 학습 탭의 일목 상태 문구와 같게(구름 위치 / 전환·기준선 / 후행스팬 / 미래 구름, 값이 null이면 "판단 불가"·tone flat)
- 화면: 시안 Main 보드 순서 — 시세 띠 → "BTC 시장 국면" 카드(가격 Mono 40, 전일 대비 ▲▼, "90일 범위 low – high", 스파크라인, 일목 상태 4칸, "학습 탭에서 차트 보기 →" 링크) + 오른쪽 KPI 카드 → "시장 메인 카드" → 기존 나머지 섹션. 기존에 보이던 정보는 모두 남긴다
- 국면 카드 실패·404·null: "학습 탭에서 BTCUSDT를 추가하면 표시됩니다" + 학습 탭 링크, 로딩 중 Skeleton

- [ ] **Step 1: 실패하는 테스트** `tests/dashboardPhase.test.ts`: 캔들 3개(종가 100→110→99) → `close 99`, `changePct ≈ -10`(소수 둘째 자리), `low/high`는 캔들 low/high 최소·최대, spark 점 3개이고 첫 x 0·마지막 x 300 / `null` 입력·캔들 1개 → `null` / 일목 상태 null 필드 → "판단 불가"·flat, `cloud_position: 'below'` → "구름 아래"·down, `tk_cross: 'golden'` → "골든크로스"·up
- [ ] **Step 2:** `npm test` → FAIL
- [ ] **Step 3:** 구현(테스트 스크립트 추가 포함)
- [ ] **Step 4:** `npm test`, `npm run build`, 변경 파일 eslint 통과
- [ ] **Step 5:** 커밋 `feat: 대시보드 새 디자인과 BTC 시장 국면 카드`

### Task 5: 학습 탭 + 가격축 선형/로그 토글

**Files (Modify):** `src/components/screens/Learning.tsx`, `src/components/learning/LearningChart.tsx`, `TradePanel.tsx`, `JournalPanel.tsx`, `ReviewPanel.tsx`, `PerformancePanel.tsx`, `BacktestPanel.tsx`, `learningShared.ts`(MUTED·DIM·TEXT → 토큰 값), `ichimokuCloud.ts`(구름 색 인자 유지)
- Test: 기존 `tests/learningChartData.test.ts` 통과 유지(`learningChartData.ts`의 SPRING/UPTHRUST 마커 색은 상승/하락 뜻이 아니므로 바꾸지 않는다)

**Interfaces:**
- `LearningChart` 색: 캔들 상승 `C.up`·하락 `C.down`, 전환선 `C.warn`, 기준선 `C.violet`, 후행스팬 `C.text3`, 선행 A/B 선과 양운·음운 채움은 `C.up`/`C.down`의 16% 투명, 지그재그 `C.text`(85%), 피보 선 `C.text3` 점선, 격자 `C.line`, 글자 `C.text3`, 배경 `C.surface`
- 가격축 토글: 차트 카드 위 툴바에 세그먼트 [선형 | 로그], 기본 선형, `priceScale().applyOptions({ mode })`로 전환(lightweight-charts `PriceScaleMode.Normal`/`Logarithmic`), 토글 상태는 `LearningChart` 안 `useState`
- 배치(시안 Learning 보드): 종목 칩 줄 → 시간봉 세그먼트 + 지표 토글 칩 + 선형/로그 + "지표 설정" → 차트 카드(flex 3) + 오른쪽 열(일목 상태 카드, 모의 주문 카드) → 일지/복기/성과/백테스트 탭 카드. 기존 기능·API 호출은 그대로
- 매수 버튼 `--up` 바탕·`--bg` 글자, 매도 `--down`

- [ ] **Step 1:** 구현
- [ ] **Step 2:** `npm test`, `npm run build`, `npx eslint src/components/learning src/components/screens/Learning.tsx` 새 오류 없음
- [ ] **Step 3:** 커밋 `feat: 학습 탭 새 디자인과 가격축 선형·로그 토글`

### Task 6: 시장분석·유동성·볼륨트래커

**Files (Modify):** `src/components/screens/Market.tsx`, `Liquidity.tsx`, `Volume.tsx`(+ `volumePutcall.ts`·`volumeUsState.ts`는 색 상수가 있을 때만)
- Test: 기존 `putcallView`·`volumeUsState` 테스트 통과 유지

**Interfaces:**
- 시안 Market/Liquidity/Volume 보드의 카드·배너·차트 색 규칙
- Market: 상태 배너(주의 = `--warn` 7% 바탕 + 28% 테두리), 지표 칩 카드, 인사이트 레벨 배지(LEVEL 색), VIX 시리즈 `C.neutralSeries`·BTC 시리즈 `C.accent`
- Liquidity: 방향 배너 공급 = `--ok`, 흡수 = `--warn`, 중립 = `--text-2`. TGA YoY 선 `C.ok`, BTC 선 `C.accent`. 최근 경매 결과 `BTC N.NNx` → **`응찰률 N.NNx`**. 50B 초과 경매 금액 `--warn`
- Volume: 업비트 `C.accent`·빗썸 `C.neutralSeries`, RSI 일봉 `C.violet`·주봉 `C.warn`, 기준선 70·75 = `C.warn`, 30·25 = `C.ok`(과열/침체 뜻), Put/Call 0.7 = `C.warn`·1.0 = `C.ok`

- [ ] **Step 1:** 구현
- [ ] **Step 2:** `npm test`, `npm run build`, 변경 파일 eslint 새 오류 없음
- [ ] **Step 3:** 커밋 `feat: 시장분석·유동성·볼륨트래커 새 디자인, 경매 응찰률 표기`

### Task 7: SPF·CVD 스크리너·고래추적

**Files (Modify):** `src/components/screens/SPF.tsx`, `Alt.tsx`(+ `cvdChartData.ts`는 색 상수가 있을 때만), `Whale.tsx`
- Test: 기존 `cvdChartData`·`whale13fView` 테스트 통과 유지

**Interfaces:**
- SPF: OI 경고 배너 CRITICAL = `--danger`, 주의 = `--warn`. 하락 위험 막대 `--warn`, 반등 기대 `--ok`. 방향 전망 상승 `--up`·하락 `--down`. 적중률 실측 55↑ `--ok`, 45↑ `--warn`, 그 아래 `--danger`. 예측 기록 칩 ✓ `--ok`, ✗ `--warn`, – `--text-2`, · `--text-3`. 흐름 라벨 색(`FLOW_COLORS`)은 롱 계열 `--up`, 숏 계열 `--down`, 중립 `--text-2`
- CVD: 주기 토글 세그먼트, 등급 S = accent 20% 바탕+accent, A = `--ok`, B = `--seg-active` 바탕, C·D = `--surface-2`. BB 스퀴즈 70↑ `--warn`, 50↑ `--neutral-series`. CVD 선 `C.info`, 가격 선 `C.accent`. 다이버전스 음영 강세(가격↓CVD↑) = `C.up` 10~12%, 약세(가격↑CVD↓) = `C.down` 10~12%. Delta 막대 양수 `C.up`, 음수 `C.down`. 팩터 막대 70↑ `--ok`, 50↑ `--accent`, 30↑ `--warn`, 그 아래 `--neutral-series`
- Whale: 합의 롱 우세 `--up`, 숏 우세 `--down`. 3색 바 롱 `--up`·숏 `--down`·중립 `--neutral-series`. 1~3위 번호 `--accent`. BTC 롱 배지 `--up` 14% 바탕, 숏 `--down`. PnL·ROI 양수 `--up`, 음수 `--down`. 한국 탭 외국인 `C.accent`·기관 `C.neutralSeries`·개인 선 `C.text2`

- [ ] **Step 1:** 구현
- [ ] **Step 2:** `npm test`, `npm run build`, 변경 파일 eslint 새 오류 없음
- [ ] **Step 3:** 커밋 `feat: SPF·CVD 스크리너·고래추적 새 디자인`

### Task 8: 리서치·리더보드·알림히스토리 + 알림 날짜 묶음

**Files:**
- Create: `dashboard/frontend/src/components/screens/alertsView.ts`
- Modify: `src/components/screens/Research.tsx`(+ `researchView.ts` 카테고리 색), `Leaderboard.tsx`, `Alerts.tsx`
- Create test: `dashboard/frontend/tests/alertsView.test.ts`

**Interfaces:**
- Produces: `groupAlertsByDay<T extends { timestamp: string }>(alerts: T[], now: Date): { label: string; date: string; items: T[] }[]` — KST 날짜(UTC+9)로 묶고 최신 날짜 먼저, 그룹 안 순서 유지. label = 오늘 / 어제 / `MM-DD`, date = `MM-DD`. 알림 시각 필드 이름은 `Alerts.tsx`의 실제 필드를 쓴다(다르면 제네릭 키 대신 그 이름으로)
- Produces: `countByLevel(alerts): { level: string; label: string; count: number }[]` — 레벨 6종(CONFIRMED_HIGH 확인 경보, HIGH 경보, LIQUIDATION_RISK 청산 위험, WHALE 고래 감지, STALE_SIGNAL 갱신 필요, MACRO_EVENT 매크로 이벤트) 순서 고정, 0건도 포함
- Alerts 화면: 머리 오른쪽 "총 N건" + 심볼 select(라벨 포함) → 레벨 건수 칩 6개 → 날짜 머리글별 알림 카드(레벨 배지, 심볼, 시각 Mono, 종목방향·시장방향 배지 급등 `--up`·급락 `--down`·중립 `--surface-2`, 기술·종합 점수 Mono). 레벨 색: 확인 경보 `--danger`, 경보 `--warn`, 청산 위험 `--violet`, 고래 감지 `--accent`, 갱신 필요 `--text-2`, 매크로 이벤트 `--info`
- Research: 필터 칩(pill, 선택 accent 테두리·12% 바탕), 카드 그리드 유지, 레벨 배지 LEVEL 색, 알트코인 24h 등락 `changeColor`
- Leaderboard: 표 9컬럼 유지, 방향 배지 롱 `--up`·숏 `--down`·– `--surface-2`, 수익·vs매수보유 `changeColor`, 1~3위 `--accent`, 선택 행 accent 7% 바탕, "시드 리셋" 버튼 `--warn-text` 테두리 버튼, 에쿼티 선 `C.accent`

- [ ] **Step 1: 실패하는 테스트** `tests/alertsView.test.ts`: now = 2026-11-19T03:00:00Z(KST 12:00)일 때 `2026-11-19T00:10:00Z`·`2026-11-18T15:00:00Z`는 "오늘", `2026-11-18T14:59:00Z`는 "어제", `2026-11-16T10:00:00Z`는 label·date `"11-16"` / 그룹 순서 최신 먼저 / `countByLevel` 6개 고정 순서, 없는 레벨 count 0, 모르는 레벨은 세지 않음
- [ ] **Step 2:** `npm test` → FAIL
- [ ] **Step 3:** 구현(테스트 스크립트 추가 포함)
- [ ] **Step 4:** `npm test`, `npm run build`, 변경 파일 eslint 새 오류 없음
- [ ] **Step 5:** 커밋 `feat: 리서치·리더보드·알림히스토리 새 디자인, 알림 날짜 묶음과 레벨 건수`

### Task 9: 남은 공용 차트·편집기 정리와 최종 색 점검

**Files (Modify):** `src/components/shared/CompositeSimulator.tsx`, `AutoBacktest.tsx`, `TuningResultTable.tsx`(경로는 실제 위치), `KrStockChart.tsx`, `TradingViewChart.tsx`, `CoinSlotEditor.tsx`, `StockSlotEditor.tsx`, `index.css`의 남은 하드코딩 색, 이번 변경으로 고아가 된 CSS

**Interfaces:**
- 대응표대로 토큰화. KrStockChart는 이미 한국식이라 값만 `C.up`/`C.down`(꼬리 50% 투명)
- 마지막 점검: `src`에서 상승 뜻 초록(`#4ade80` `#22c55e` `#36c273` `#10b981`)과 옛 slate 팔레트(`#1e293b` `#334155` `#0f172a` `#94a3b8` `#64748b` `#475569` `#e2e8f0` `#cbd5e1`) grep 결과를 보고서에 붙이고, 남은 것은 파일:줄과 남긴 이유(차트 시리즈 고유색 등)를 적는다

- [ ] **Step 1:** 구현
- [ ] **Step 2:** `npm test`, `npm run build`, `npx eslint src` 결과가 시작 시점(문제 7개: 오류 6·경고 1) 이하
- [ ] **Step 3:** 커밋 `refactor: 남은 공용 차트·편집기 색을 디자인 토큰으로 정리`
