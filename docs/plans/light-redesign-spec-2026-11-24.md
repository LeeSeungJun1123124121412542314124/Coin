# 밝은 시안(11-24) 앱 적용 스펙

- 작성일: 2026-11-24
- Seed: `seed_acc808af9330` (ouroboros, 세션 합의 내용으로 생성)
- 시안: 디자인 캔버스 "밝은 시안 11-24" — `V3Home`, `V3HomeMobile`, `V3Records`, `V3RecordsMobile`

## 1. 목표

앱(`dashboard/frontend`)을 시안과 같은 모양으로 바꾼다.

- 아이보리 바탕 · 먹색 글자 · 금색 강조의 밝은 테마 (어두운 테마는 남기지 않는다)
- 왼쪽 세로 메뉴 대신 위쪽 가로 메뉴 5개 + 맨 위 시세 띠
- 모바일은 먹색 바탕 글자 탭 5개 (더보기 시트 없음)
- 홈: 오늘의 판단 · 분석 신호판 · 청산 구간 막대 · 어제와 달라진 것 · 봇이 보낸 소식
- 리서치: 카드 격자 대신 줄 목록 (점수 분석 / 봇 관찰)

## 2. 사용자 결정 (원문)

- "너무 백년해로랑 색이 같잖아 색은 좀 다르게 해"
- "UI가 너무 똑같아서 좀 별루야 차별화를 뒀으면 좋겠어"
- "폰트는 아까 그게 좋고 UI는 마음에 든다" → 제목도 고딕(Noto Sans KR), 명조 안 씀
- "바로 앱에 적용"

## 3. 하지 않는 것

- 주소(라우트 12개) 변경 없음. 메뉴 묶음만 바뀐다.
- 홈의 기존 구역(가격 띠 · 핵심 지표 · 뉴스 · 미국/한국 주식 · 알트시즌 · 시장 상세 · 매크로)은 지우지 않고 새 구역 아래에 둔다.
- 새 패키지 설치 없음.
- 시안에 없는 화면(시장 · 파생 · 학습 · 차트)은 구조를 바꾸지 않고 색 · 틀만 새 테마를 따른다.
- 예전부터 쓰이지 않는 CSS(`.app-*` 등)는 지우지 않는다.

## 4. 색 · 글꼴 토큰

`src/index.css :root`와 `src/lib/theme.ts`의 `C`를 같은 값으로 둔다.

| 토큰 | 값 | 쓰임 |
|---|---|---|
| `--bg` | `#F8F6F1` | 바탕 |
| `--bg-inset` | `#F1EEE6` | 들어간 바탕 |
| `--surface` | `#FDFCF9` | 상자 바탕 |
| `--surface-2` | `#EFEBE2` | 뼈대 · 보조 바탕 |
| `--border` | `#DDD8CC` | 상자 테두리 |
| `--line` | `#E7E2D7` | 줄 구분선 |
| `--seg-active` | `#FFFFFF` | 선택된 세그먼트 |
| `--border-strong` | `#BDB6A6` | 진한 테두리 |
| `--text` / `--text-2` / `--text-3` | `#25231F` / `#45413A` / `#6A655C` | 글자 |
| `--accent`, `--link` | `#7A5A14` | 강조 글자 · 링크 |
| `--link-hover` | `#5C430C` | |
| `--up` / `--down` | `#B93A2E` / `#2459B0` | 한국식 등락 |
| `--warn`, `--warn-text` | `#9C4A10` | 경계 |
| `--ok` | `#2C5C45` | 강세 · 정상 |
| `--danger` | `#A8392B` | 위험 |
| `--violet` / `--info` / `--neutral-series` | `#6B4BB8` / `#3F56B5` / `#8F897E` | 구분용 |
| `--gold` | `#B8923F` | 로고 바탕 · 선택 밑줄 |
| `--gold-on-ink` | `#E3C88F` | 먹색 바탕 위 선택 글자 |
| `--on-ink-2` | `#B5AFA3` | 먹색 바탕 위 보조 글자 |
| `--up-on-ink` / `--down-on-ink` | `#F29A8B` / `#9DBDF5` | 먹색 띠 위 등락 |
| `--radius-card` | `4px` | |
| `--shadow-card` | `none` | |
| `--font-sans`, `--font-mono` | `'Noto Sans KR', system-ui, sans-serif` | 숫자도 고딕, `body`에 `tabular-nums` |

- 등급 색: 위험 = `danger`, 경계 = `warn`, 중립 = `text-2`, 강세 = `ok`(초록), 약세 = `down`.
- PWA: `theme-color`는 시세 띠 색 `#25231F`, `background_color`는 `#F8F6F1`.
- TradingView 위젯은 `theme: 'light'`.

## 5. 틀 (App.tsx · navGroups.ts)

묶음 5개 (`NAV_GROUPS`):

| 묶음 | 짧은 이름 | 화면 |
|---|---|---|
| 홈 | 홈 | `/` |
| 시장 | 시장 | `/market`, `/liquidity`, `/volume` |
| 파생 · 온체인 | 파생 | `/spf`, `/cvd`, `/whale` |
| 기록 | 기록 | `/research`, `/alerts`, `/bot-reports`, `/leaderboard` |
| 학습 | 학습 | `/learning` |

- `shell-ticker`: 먹색 띠. `/api/dashboard` 코인 슬롯의 24시간 등락, 오른쪽에 최종 갱신 시각(실패 시 "갱신 실패 · 마지막 성공 …").
- `shell-masthead`: 로고 + 묶음 5개(묶음의 첫 화면으로 이동, 현재 묶음은 금색 밑줄). 모바일에서는 로고만.
- `shell-subnav`: 현재 묶음에 화면이 둘 이상이면 그 화면들의 밑줄 탭.
- 화면 제목 · 설명(`shell-title`, `shell-desc`)은 홈에서는 숨긴다(판단 제목이 그 자리).
- `shell-bottom`: 모바일 고정 아래 탭. 먹색 바탕, 글자만, 묶음 5개.
- 없애는 것: `shell-sidebar`, 더보기 시트, 메뉴 아이콘, `MOBILE_PRIMARY`.

## 6. 홈 (Dashboard.tsx + HomeBrief)

위에서부터:

1. 오늘의 판단 — 기존 `summarizeMood` 결과. 머리말(예: "조심할 구간")을 큰 제목으로, 꼬리말과 근거 집계를 본문으로, 근거 4개는 줄 목록 링크로.
2. 분석 신호판 — `/api/research-analysis`의 점수 분석 카테고리마다 한 칸(색 막대 · 이름 · 등급), 급한 순. 누르면 `/research`.
3. 비트코인 — 현재가 · 24시간 등락. 봇 히트맵 카드에 `details.levels`(현재가 · 아래 롱 · 위 숏)가 있으면 그 사이 위치 막대.
4. 어제와 달라진 것 — 점수 분석을 급한 순으로 4개까지: 등급 · 이름 · 요약 · 어제 대비 점수 변화(이전 기록 없으면 "–").
5. 봇이 보낸 소식 — 봇 관찰 카드: 시각 · 이름 · 요약. 없으면 구역을 그리지 않는다.
6. 기존 구역 그대로.

백엔드: `bot_cards.py`의 히트맵 카드 `details`에 `levels: {price, long_price, short_price}`(없는 값은 빼고)를 추가한다.

## 7. 리서치 (Research.tsx)

- 카테고리 걸러 보기 칩, 상세 펼침, 어제 · 7일 전 대비 줄은 그대로.
- "점수 분석 N개"와 "봇 관찰 N개" 두 구역, 각 구역은 굵은 윗줄 + 가는 줄로 나눈 두 단 목록(모바일 한 단).
- 한 줄: 등급(작은 네모 + 글자) · 이름 · 제목 · 요약, 오른쪽에 점수 큰 숫자 + 가는 막대.

## 8. 검증

| 단계 | 방법 |
|---|---|
| 토큰 | `npm test`(themeTokens), `pytest dashboard/tests/test_pwa_assets.py` |
| 틀 | `tests/navGroups.test.ts`, `pytest dashboard/tests/test_mobile_app_shell.py` 등 셸 계약 테스트(새 구조로 고침) |
| 홈 · 리서치 | 새 순수 함수 테스트(`homeBriefView`), 기존 화면 계약 테스트 |
| 백엔드 | `pytest dashboard/tests/test_bot_cards.py` |
| 전체 | `npm test`, `npm run build`, `npx tsc -b --noEmit`, `pytest dashboard/tests -q` |
| 화면 | 로컬(운영 DB 사본)에서 PC 1440 · 모바일 390으로 12개 화면을 열어 글자 대비 · 가로 넘침 확인 |
