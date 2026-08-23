# SPF 3단계 — 재가중 브랜치 병합 + 가중치 산출·전후 비교 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 브랜치 `spf-phase3-reweight`를 master에 병합해 `derive_weights`를 사용 가능하게 만들고, 프로덕션 리더보드 실측으로 가중치를 산출한 뒤, 8년 백테스트로 동등가중 대비 개선 여부를 수치로 뽑아 **사람 판정 직전까지** 진행한다.

**Architecture:** 새 계산 로직을 만들지 않는다. 병합 + 이미 있는 함수·스크립트 실행 + 산출물 기록뿐이다. `derive_weights` 산출식은 **판정 대상이지 수정 대상이 아니다.**

**Tech Stack:** Python 3.12 / pandas / pytest / git / Railway CLI 4.40.0

---

## 이 계획의 위치

상위 계획서 [`spf-phase3-reweight-2026-08-23.md`](spf-phase3-reweight-2026-08-23.md)의 **Task 2 전체 + Task 3 진입 직전**까지다. 상위 Task 1(`n_days_equity`)은 커밋 `c693b3d`로 완료·push됐다.

| 이 계획 | 상위 계획서 대응 |
|---|---|
| Task 1 | (신규) 브랜치 병합 — 상위 계획서가 "선행 조건"으로만 언급하고 절차를 안 적었다 |
| Task 2 | Task 2 Step 2 (프로덕션 스냅샷 조회) |
| Task 3 | Task 2 Step 3 (가중치 산출) |
| Task 4 | Task 2 Step 4 (백테스트 전후 비교) |
| Task 5 | Task 2 Step 5~6 (산출물 커밋 + 보고 후 정지) |

**Task 5에서 멈춘다.** 상위 계획서 Task 3(채택 게이트)은 **사람이 판정**하고, Task 4(프로덕션 배선)는 채택된 뒤의 일이다.

### 배경 — 왜 병합이 먼저인가

상위 계획서 Task 1이 리더보드에 `n_days_equity`를 추가한 이유는 `derive_weights`의 소표본 가드에 그 필드를 물리기 위해서다. 그런데 정작 **`derive_weights`가 사는 `crypto-volatility-bot/app/macro/factor_weights.py`가 master에 없다.** 재가중 계산부는 커밋 `673a315`(브랜치 `spf-phase3-reweight`)에 있고 아직 병합되지 않았다. 병합 없이는 Task 3을 실행할 수 없다.

### 사전 확인 (2026-08-23 실측)

```
master              = c693b3d  (origin/master와 동일, 미푸시 0)
spf-phase3-reweight = 673a315  (master보다 +1커밋)
```

**충돌 없음이 확인됐다.** `673a315`가 건드리는 7개 파일은 전부 `crypto-volatility-bot/` 아래이고, master가 분기점(`6bc27a5`) 이후 건드린 파일은 `dashboard/backend/services/paper_engine.py`, `dashboard/tests/test_paper_engine.py`, `docs/plans/spf-phase3-reweight-2026-08-23.md` 셋뿐이라 겹치지 않는다.

**테스트 기준선 (2026-08-23 실측):**

| | 병합 전 (현재 master) | 병합 후 기대 |
|---|---|---|
| 봇 `tests/unit` | 339 | **348** (+9) |
| 봇 `tests` 전체 | 347 | **356** (+9) |
| 대시보드 `dashboard/tests` | 220 | **220** (불변) |
| 합계 | 567 | **576** |

### 실행 환경

```bash
# 봇 테스트·스크립트 — cwd가 crypto-volatility-bot 이어야 app... 임포트됨
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -m pytest tests -q

# 대시보드 테스트 — repo 루트에서 "시스템 python" (공용 venv엔 apscheduler가 없다)
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

Railway CLI는 연결·인증돼 있다 (`Project: Coin-DashBorad / Environment: production / Service: Coin`).

---

## File Structure

| 파일 | 역할 | 변경 |
|---|---|---|
| `crypto-volatility-bot/app/macro/factor_weights.py` | `derive_weights` | 병합으로 **유입** (Task 1) |
| `crypto-volatility-bot/app/macro/direction_composite.py` | `compute_composite(..., weights=)` | 병합으로 수정분 유입 (Task 1) |
| `crypto-volatility-bot/scripts/composite_history.py` | `--weights-json` 비교 CLI | 병합으로 수정분 유입 (Task 1) |
| `crypto-volatility-bot/data/leaderboard_snapshot.json` | **신규 산출물** 프로덕션 실측 스냅샷 | Task 2가 생성 |
| `crypto-volatility-bot/data/factor_weights.json` | **신규 산출물** 산출 가중치 + 근거 메타 | Task 3이 생성 |
| `crypto-volatility-bot/data/composite_sources.csv` | 8년 원시 소스 (2026-07-11자, 258KB) | **읽기만** |

---

### Task 1: 브랜치 `spf-phase3-reweight` 병합

- [ ] **Step 1: 병합 전 상태 확인**

```bash
cd /e/Dev/coin
git status --short | grep -v '^??'
git log --oneline -1 master
git log --oneline -1 spf-phase3-reweight
```

Expected: 수정/스테이징 항목 **없음**(untracked `??`만), master = `c693b3d`, 브랜치 = `673a315`.
다르면 멈추고 보고한다.

- [ ] **Step 2: 병합**

master와 브랜치가 갈라져 있으므로 fast-forward가 아닌 **병합 커밋**이 생긴다. rebase 하지 말 것 — 브랜치는 이미 다른 워크트리에 체크아웃돼 있다.

```bash
cd /e/Dev/coin
git merge --no-ff spf-phase3-reweight -m "$(cat <<'EOF'
Merge branch 'spf-phase3-reweight' — SPF 3단계 재가중 계산부

가중평균 compute_composite(weights=), derive_weights, 전후 비교 CLI를
master로 들인다. weights 생략 시 기존 동등가중과 동일해 기존 호출부는
영향받지 않는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

충돌이 나면 **해결하지 말고 `git merge --abort` 후 멈추고 보고**한다. 사전 분석상 충돌은 없어야 하며, 나온다면 전제가 틀린 것이다.

- [ ] **Step 3: 병합 결과 확인**

```bash
cd /e/Dev/coin
git log --oneline -3
ls crypto-volatility-bot/app/macro/factor_weights.py
```

Expected: 병합 커밋이 최상단, `factor_weights.py`가 존재한다.

- [ ] **Step 4: 양쪽 테스트 전체 회귀**

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -m pytest tests -q
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

Expected: 봇 **356 passed**, 대시보드 **220 passed**, 실패 0건.
수가 다르면 그대로 기록하고 보고한다.

- [ ] **Step 5: 동등가중 베이스라인 무오염 확인**

병합이 기존 경로를 건드리지 않았는지 본다. `backtest_baseline.build_history_frame`은 `compute_composite`을 인자 없이 부르므로 동등가중이 유지돼야 한다.

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe scripts/composite_history.py --from-csv data/composite_sources.csv
```

Expected: 방향적중 **7일 56.5 / 14일 58.6 / 30일 61.4 / 60일 64.5**.
**다르면 멈추고 보고한다** — 베이스라인이 바뀌면 이후 전후 비교가 무의미해진다.

- [ ] **Step 6: 커밋 확인 (병합 커밋은 Step 2에서 이미 생성됨)**

```bash
cd /e/Dev/coin
git status --short | grep -v '^??' || echo "clean"
```

Expected: `clean`. **push하지 않는다** — 이 계획은 push를 포함하지 않는다.

---

### Task 2: 프로덕션 리더보드 스냅샷 조회

- [ ] **Step 1: 조회 스크립트 작성 후 base64로 감싸 실행**

`railway ssh`는 명령을 `sh -c`로 넘기며 따옴표를 깨뜨리므로 base64로 감싼다(상위 계획서에서 검증된 방법).

**⚠️ 이 스텝은 반드시 Git Bash에서 실행한다.** 아래 명령은 POSIX 셸 문법이다. Windows PowerShell 5.1에서 돌리면 중첩 따옴표가 깨져 원격에서 구문 오류가 나고, `ProcessStartInfo.ArgumentList`로 우회하려 해도 PS 5.1(.NET Framework)에는 그 속성이 없어 실패한다(2026-08-23 실측 — 3회 연속 실패). PowerShell만 쓸 수 있는 실행 주체라면 이 스텝을 수행하지 말고 **사람에게 넘긴다.**

```bash
cd /e/Dev/coin
printf '%s\n' \
"import sys,json" \
"sys.path.insert(0,'/app')" \
"sys.path.insert(0,'/app/crypto-volatility-bot')" \
"from dashboard.backend.services.paper_engine import leaderboard" \
"rows=leaderboard()" \
"print(json.dumps([{k:r[k] for k in ('indicator','sharpe','n_days_equity','total_return_pct','n_trades')} for r in rows],ensure_ascii=False))" \
> /tmp/lb.py
B64=$(base64 -w0 /tmp/lb.py)
railway ssh "python -c \"import base64;exec(base64.b64decode('$B64'))\""
```

- [ ] **Step 2: 배포 반영 여부 판정 — ⛔ 게이트**

**출력 JSON의 모든 행에 `n_days_equity` 키가 있어야 한다.**

- `KeyError: 'n_days_equity'`가 나거나 키가 비어 있으면 → **커밋 `c693b3d`의 Railway 배포가 아직 안 끝난 것이다.** 여기서 **멈추고 보고**한다. 재시도는 사람이 지시한다. 필드를 임의로 만들어 넣거나 우회하지 말 것.
- 은퇴 지표(달러·금리·TGA·RSI·모멘텀30d)가 목록에 **없어야** 한다(`leaderboard()`가 현재 레지스트리만 반환). 있으면 기록하고 보고한다.

- [ ] **Step 3: 스냅샷 저장**

출력 JSON 배열을 그대로 저장한다.

```bash
# 위 출력을 crypto-volatility-bot/data/leaderboard_snapshot.json 에 기록
```

확인:

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -c "
import json
rows = json.load(open('data/leaderboard_snapshot.json', encoding='utf-8'))
print(f'{len(rows)}개 지표')
for r in sorted(rows, key=lambda x: -(x['sharpe'] or 0)):
    print(f\"  {r['indicator']:<8} sharpe={r['sharpe']:>7.3f}  일수={r['n_days_equity']:>4}  거래={r['n_trades']:>3}  수익={r['total_return_pct']:>7.1f}%\")
"
```

Expected: 9개 지표(복합방향·순유동성·VIX·MVRV·볼린저밴드·도미넌스·유동성·긴축환경·과열회귀). 매수보유는 벤치마크라 제외돼 있다.

---

### Task 3: 가중치 산출

- [ ] **Step 1: `derive_weights` 실행**

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -c "
import json
from app.macro.factor_weights import derive_weights
snap = json.load(open('data/leaderboard_snapshot.json', encoding='utf-8'))
out = derive_weights(snap)
json.dump(out, open('data/factor_weights.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
for k, v in sorted(out['weights'].items(), key=lambda kv: -kv[1]):
    print(f'{k:<20} {v:.4f}')
print('경계 포화:', sum(1 for v in out['weights'].values() if v in (0.5, 2.0)), '/ 9')
"
```

Expected(2026-08-23 예측): 6개가 경계값(0.5 또는 2.0)에 붙고, 리더보드 대응이 없는 `active_addr_13w`·`sma50_dist`·`momentum_30d` 3개가 1.0.
**다른 양상이면 그대로 기록하고 보고한다** — 예측이 빗나간 것 자체가 정보다.

- [ ] **Step 2: 매핑 평균 Sharpe 부호 확인 — ⛔ 게이트**

상위 계획서 Task 3 채택 게이트의 5번째 항목이다. `derive_weights`는 `sharpe_i / mean(sharpe)`로 나누므로 **평균이 음수면 가중치 순위가 통째로 역전된다**(좋은 팩터 0.5, 나쁜 팩터 2.0). 경고 없이 조용히 일어나므로 수치로 직접 본다.

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -c "
import json
from app.macro.factor_weights import _INDICATOR_FACTOR_MAP
rows = json.load(open('data/leaderboard_snapshot.json', encoding='utf-8'))
vals = []
for r in rows:
    fs = _INDICATOR_FACTOR_MAP.get(r['indicator'])
    if not fs or r['sharpe'] is None or r['n_days_equity'] < 30:
        continue
    vals += [r['sharpe'] / len(fs)] * len(fs)
mean = sum(vals) / len(vals)
print(f'매핑 대상 {len(vals)}개, 합 {sum(vals):+.4f}, 평균 {mean:+.4f}')
print('판정:', '양수 — 진행 가능' if mean > 0 else '음수 — 가중치 역전, 채택 불가')
"
```

Expected: `평균 +0.0842` 근처의 **양수**.

**음수가 나오면 여기서 멈추고 보고한다.** 산출식을 고치지 말 것 — 상위 계획서 Non-Goals다. 음수는 "지금 표본으로는 재가중을 채택하지 않는다"는 결론이며, 그것도 유효한 결과다.

---

### Task 4: 백테스트 전후 비교

- [ ] **Step 1: 비교 실행**

```bash
cd /e/Dev/coin/crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe scripts/composite_history.py \
  --from-csv data/composite_sources.csv --weights-json data/factor_weights.json
```

Expected: 기존 베이스라인 표에 이어 **"동등가중 vs 재가중 비교"** 표가 H7/14/30/60 적중률·IC로 출력된다.

- [ ] **Step 2: 베이스라인 무결성 재확인 — ⛔ 게이트**

같은 출력의 베이스라인 표가 **7일 56.5 / 14일 58.6 / 30일 61.4 / 60일 64.5**인지 본다.
다르면 소스 CSV나 경로가 바뀐 것이므로 **멈추고 보고**한다. 비교 자체가 무효가 된다.

- [ ] **Step 3: 비교표 4개 호라이즌 전부 기록**

적중률과 IC를 **둘 다** 옮겨 적는다. 판정은 사람이 하므로 유리한 숫자만 고르지 말 것.

---

### Task 5: 산출물 커밋 + 보고 후 정지

- [ ] **Step 1: 산출물 커밋**

```bash
cd /e/Dev/coin
git add crypto-volatility-bot/data/leaderboard_snapshot.json crypto-volatility-bot/data/factor_weights.json
git commit -m "$(cat <<'EOF'
chore: SPF 재가중 실측 스냅샷·산출 가중치 기록

프로덕션 리더보드 forward 실측에서 뽑은 스냅샷과 derive_weights
산출 결과. 채택 여부와 무관하게 판정 근거로 남긴다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: 보고 후 종료 — ⛔ 여기서 멈춘다**

다음을 **그대로** 보고한다. 채택 여부는 사람이 판정한다:

1. 스냅샷 원본 — 지표별 Sharpe / `n_days_equity` / 거래수 / 총수익
2. 산출된 9팩터 가중치 — 경계값(0.5·2.0)에 몇 개가 붙었는지
3. **매핑 평균 Sharpe의 부호와 값**
4. 전후 비교표 — H7/14/30/60 **적중률과 IC 전부**
5. 거래 0건인 지표가 받은 가중치 (표본 1개짜리가 최대 가중치를 받는 구조인지)

**진행하지 않을 것:** 채택 판정, 프로덕션 배선(상위 계획서 Task 4), `FACTOR_WEIGHTS` 상수 추가, `COMPOSITE_VERSION` 태깅, push.

---

## 제약 (전 태스크 공통)

- **한국어** 주석·문서
- **외과적 변경** — 이 계획은 병합·실행·기록만 한다. **소스 코드를 한 줄도 새로 쓰지 않는다.** 코드를 고치고 싶어지면 멈추고 보고한다
- **`derive_weights`의 산출식(Sharpe 평균 나누기, 0.5~2.0 클립, 결합지표 분할)은 고치지 않는다** — 판정 대상이지 수정 대상이 아니다(상위 계획서 Non-Goals)
- **`crypto-volatility-bot/app/macro/backtest_baseline.py`는 건드리지 않는다** — 인자 없이 `compute_composite`을 불러야 동등가중 베이스라인이 유지된다
- **push 금지.** 이 계획에 push는 없다. 배포 시점은 채택 판정 후 사람이 정한다
- **`git add`는 각 스텝에 명시된 경로만.** 저장소 루트에 untracked 파일이 다수 있다(`.mcp.json`, `crypto_dump.sql`, `crypto_inserts.sql`, `ohlcv_inserts.sql`, `crypto_b64.txt`, `.ouroboros_eval_artifact.md`, `docs/plans/*.md` 일부) — **`git add .` / `git add -A` 절대 금지**
- **새 패키지 설치 금지**
- 커밋 메시지는 `type: 한국어 설명` + 본문 마지막 줄 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- 게이트(⛔)에서 기대와 다르면 **우회하지 말고 멈추고 보고**한다

## Non-Goals

- 채택 판정 (상위 계획서 Task 3) — 사람이 한다
- 프로덕션 배선 (상위 계획서 Task 4) — 채택된 뒤의 일
- `derive_weights` 산출식 개선 (클립 포화 · 거래 0건 표본 · 부호 역전 자체의 해결)
- push 및 Railway 배포
- 백테스트 소스 CSV 갱신 (현재 2026-07-10까지 — 8년 표본에서 6주는 결과를 바꾸지 않는다)
- 13F 작업, 스테일 워크트리 정리 등 다른 갈래

## Self-Review

- **범위 커버리지:** 병합(Task 1) → 스냅샷(Task 2) → 산출(Task 3) → 비교(Task 4) → 기록·정지(Task 5). 상위 계획서 Task 2 Step 2~6에 1:1 대응하고, 상위 계획서가 절차를 안 적어둔 병합을 Task 1로 앞에 세웠다.
- **게이트 4개:** 배포 미반영(Task 2 Step 2), 평균 Sharpe 음수(Task 3 Step 2), 베이스라인 변동(Task 1 Step 5 / Task 4 Step 2), 병합 충돌(Task 1 Step 2). 전부 "멈추고 보고"이고 우회 금지를 명시했다.
- **플레이스홀더:** 없음. 모든 스텝에 실행 명령과 기대 출력이 있다. Task 2 Step 3의 저장 내용만 실행 결과라 사전에 알 수 없고, 저장 후 확인 명령을 붙였다.
- **실측 확인:** 테스트 기준선(봇 339→348, 전체 347→356, 대시보드 220), 충돌 없음(파일 겹침 0), `composite_sources.csv` 존재(258KB), Railway 연결 상태 — 전부 2026-08-23 직접 확인.
- **이름 일관성:** `derive_weights`, `_INDICATOR_FACTOR_MAP`, `n_days_equity`, `data/leaderboard_snapshot.json`, `data/factor_weights.json`, `composite_sources.csv` — 전 태스크에서 동일.
