# SPF 3단계 Task 1 — `n_days_equity` 연결 + 판정 게이트 보강 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 리더보드 집계에 `n_days_equity` 필드를 추가해 재가중 표본 가드를 연결하고, 상위 계획서의 채택 게이트에 "매핑 대상 평균 Sharpe 부호 확인" 항목을 보강한 뒤, master를 origin에 push한다.

**Architecture:** 코드 변경은 `dashboard/backend/services/paper_engine.py`의 순수 함수 `_curve_stats` 반환 dict에 필드 하나를 더하는 것뿐이다(두 군데 반환 경로). 나머지는 마크다운 문서 수정과 push다. 새 모듈·새 계산 로직 없음.

**Tech Stack:** Python 3.12 / pytest (시스템 python) / git

---

## 이 계획의 범위 (자족적 — 상위 계획서를 안 봐도 실행 가능)

상위 계획서 [`docs/plans/spf-phase3-reweight-2026-08-23.md`](spf-phase3-reweight-2026-08-23.md)는 Task 1~4로 구성돼 있고 아직 하나도 체크되지 않았다. **이번에 확정된 범위는 그중 Task 1과, 상위 계획서 문서 자체의 수정 하나, 그리고 push까지다.**

| 이 계획 | 상위 계획서 대응 | 성격 |
|---|---|---|
| Task 1 | Task 3 "채택 게이트" 체크리스트 + "⚠️ 판정 시 반드시 볼 것" 절 | 문서 수정 (코드 아님) |
| Task 2 | Task 1 (Step 1~5) 전체 | 코드 (TDD) |
| Task 3 | Task 2 Step 1의 `git push origin master` | 배포 트리거 |

**여기서 멈춘다.** 상위 계획서 Task 2 Step 2(`railway ssh` 스냅샷 조회) 이후는 **이번 범위 밖**이다. Task 3의 push가 끝나면 결과를 보고하고 종료한다. 절대 스냅샷 조회·가중치 산출·백테스트 비교로 넘어가지 말 것.

### 배경 — `n_days_equity`가 왜 필요한가

봇 쪽 `derive_weights(리더보드_스냅샷)`(가중치 산출 함수)는 각 행의 `row["n_days_equity"]`를 읽어 **에쿼티 관측일이 30일 미만이면 그 팩터 가중치를 1.0으로 고정**하는 소표본 가드를 건다. 그런데 그 필드의 생산자가 저장소에 없다 — 테스트 fixture에만 존재한다. 지금 연결하면 `KeyError: 'n_days_equity'`가 난다. 이 계획의 Task 2가 그 생산자를 만든다.

### 알려진 선행 조건 (이번 범위 밖, 참고용)

`derive_weights`가 사는 파일 `crypto-volatility-bot/app/macro/factor_weights.py`는 **master에 존재하지 않는다.** 재가중 계산부는 커밋 `673a315`(브랜치 `spf-phase3-reweight`)에 있고 아직 master에 병합되지 않았다. 따라서 상위 계획서 Task 2 Step 3(가중치 산출)은 그 브랜치를 병합해야 실행 가능하다. **이번 계획은 그 병합을 하지 않는다** — Task 2가 추가하는 `n_days_equity`는 소비자가 없어도 그 자체로 무해한 리더보드 필드 하나이므로 순서 의존이 없다.

### 사전 확인 — git 상태 (놀라지 말 것)

작업 시작 시점:

```
master     = 7ece00d  docs: SPF 3단계 계획서 재작성 — 리더보드 forward 실측 기반으로 정정
             6bc27a5  docs: SPF 3단계 재가중 구현 계획 작성
origin/master = 138b2fd  docs: DATABASE_PATH 실제 경로를 /app/data/crypto.db로 정정
```

**master가 origin보다 2커밋 앞서 있다**(`7ece00d`, `6bc27a5` — 둘 다 docs, 미푸시). 따라서 Task 3의 `git push origin master`는 **이 2개 + 이 계획이 만드는 커밋 2개, 총 4커밋**을 한꺼번에 올린다. 정상이다. push 전에 `git log --oneline origin/master..HEAD`로 올라갈 목록을 눈으로 확인만 하고 그대로 진행한다.

저장소 루트에 추적되지 않는 파일이 많다(`.mcp.json`, `.ouroboros_eval_artifact.md`, `crypto_b64.txt`, `crypto_dump.sql`, `crypto_inserts.sql`, `ohlcv_inserts.sql`, `docs/plans/us-13f-institution-holdings-2026-08-23.md`, `docs/plans/spf-phase3-reweight-impl-2026-08-23.md`). **`git add .` 절대 금지.** 아래 각 커밋 스텝에 적힌 경로만 `git add` 한다.

### 실행 환경 (중요)

봇과 대시보드는 같은 저장소의 다른 하위 디렉터리이고 테스트 실행 방법이 다르다.

```bash
# 대시보드 테스트 — repo 루트에서 "시스템 python"
# (공용 venv에는 apscheduler가 없어서 임포트 단계에서 깨진다)
cd /e/Dev/coin
python -m pytest dashboard/tests -q

# 봇 테스트 — cwd가 crypto-volatility-bot 이어야 app... 임포트됨
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -m pytest tests/unit -q
```

이 계획은 대시보드 파일만 건드리므로 **봇 테스트는 실행할 필요가 없다.** 위 명령은 참고용으로만 적어 둔다.

---

## File Structure

| 파일 | 역할 | 이 계획에서의 변경 |
|---|---|---|
| `docs/plans/spf-phase3-reweight-2026-08-23.md` | 상위 계획서 | 수정 (Task 1) — 판정 체크리스트 1항목 추가 + 배경 절 1문단 보강 |
| `dashboard/backend/services/paper_engine.py` | 리더보드 집계. `_curve_stats`(200행)가 에쿼티 곡선 통계 dict를 만든다 | 수정 (Task 2) — 반환 dict **두 곳**에 `n_days_equity` 추가 |
| `dashboard/tests/test_paper_engine.py` | 리더보드 집계 테스트. `_curve_stats`는 파일 상단 9행에서 이미 import돼 있다 | 수정 (Task 2) — 테스트 2건 추가 |

---

### Task 1: 상위 계획서 채택 게이트에 "평균 Sharpe 부호 확인" 추가 (문서 수정, 코드 아님)

**왜:** `derive_weights`는 `sharpe_i / mean(sharpe of 매핑 대상)`으로 가중치를 만든다. 2026-08-23 실측 스냅샷 기준 매핑 대상 6개의 Sharpe 합은 **+0.505**, 평균은 **+0.0842**로 아슬아슬하게 양수다.

| 매핑 대상 | Sharpe |
|---|---|
| 순유동성 (`net_liquidity_13w`) | -1.043 |
| VIX (`vix_level`) | -2.947 |
| MVRV (`mvrv_level`) | +2.910 |
| 긴축환경 ÷2 (`dxy_13w`) | +0.405 |
| 긴축환경 ÷2 (`ust10y_13w`) | +0.405 |
| 과열회귀 (`rsi14`) | +0.775 |
| **합 / 평균(6개)** | **+0.505 / +0.0842** |

평균이 음수로 넘어가면 나눗셈의 **부호가 뒤집혀 가중치 순위가 통째로 역전**된다 — 좋은 팩터가 0.5를, 나쁜 팩터가 2.0을 받는다. 예외도 경고도 없이 조용히 일어난다. VIX Sharpe가 지금의 -2.947에서 **-3.45 부근까지만 더 나빠져도**(합이 0.505만큼 줄면) 평균이 음수가 된다.

상위 계획서는 "평균이 0에 근접 → 클립 포화"만 경고하고 **부호 역전은 한 줄도 언급이 없다.** 이 Task가 그 공백을 메운다.

**⚠️ 이것은 순수하게 "판정 체크리스트 항목 추가"다. 산출식은 절대 고치지 않는다.** 상위 계획서의 제약 *"`derive_weights`의 산출식(Sharpe 평균 나누기, 0.5~2.0 클립, 결합지표 분할)은 고치지 않는다 — 판정 대상이지 수정 대상이 아니다"* 와 Non-Goals(*"`derive_weights` 산출식 개선(클립 포화·거래 0건 표본 문제)"*)는 **그대로 유지**한다. 이 Task에서 `.py` 파일을 여는 일은 없다.

**Files:**
- Modify: `docs/plans/spf-phase3-reweight-2026-08-23.md` (2군데 — 55~57행 근처, 262행 근처)

- [ ] **Step 1: "⚠️ 판정 시 반드시 볼 것" 절에 부호 역전 문단 보강**

`docs/plans/spf-phase3-reweight-2026-08-23.md`에서 아래 두 줄 사이(현재 55행 문단 끝과 57행 문단 시작 사이)에 새 문단을 끼워 넣는다.

찾을 문자열 (이 두 문단은 빈 줄 하나로 붙어 있다):

```
즉 실질적으로 **"Sharpe 양수면 2.0, 음수면 0.5"** 인 이진 규칙이 된다.

또 **MVRV는 거래 0건**이다
```

바꿀 문자열:

```
즉 실질적으로 **"Sharpe 양수면 2.0, 음수면 0.5"** 인 이진 규칙이 된다.

**평균이 0 근처라는 것은 "부호 역전" 위험도 함께 뜻한다.** 매핑 대상 6개의 Sharpe 합은 **+0.505**, 평균은 **+0.0842**로 아슬아슬하게 양수다(순유동성 -1.043 · VIX -2.947 · MVRV +2.910 · 긴축환경 0.810을 반으로 나눈 +0.405 두 개 · 과열회귀 +0.775). 평균이 **음수로 넘어가면 `sharpe_i / mean(sharpe)`의 부호가 뒤집혀 가중치 순위가 통째로 역전**된다 — 좋은 팩터가 0.5를, 나쁜 팩터가 2.0을 받는다. 예외도 경고도 없이 조용히 일어난다. VIX Sharpe가 지금의 **-2.947에서 -3.45 부근까지만 더 나빠져도** 합이 0을 넘는다. 클립 포화와는 별개의 문제이므로 Task 3에서 **평균의 부호를 수치로 직접 확인**한다.

또 **MVRV는 거래 0건**이다
```

- [ ] **Step 2: Task 3 "채택 게이트" 판정 체크리스트에 5번째 항목 추가**

같은 파일의 Task 3 Step 1 체크리스트(현재 적중률·IC·클립 포화·MVRV 거래 0건 4개)에 다섯 번째를 더한다.

찾을 문자열:

```
- **MVRV 거래 0건**: 포지션 1개짜리 표본이 최대 가중치를 받는 구조를 수용할지
```

바꿀 문자열:

```
- **MVRV 거래 0건**: 포지션 1개짜리 표본이 최대 가중치를 받는 구조를 수용할지
- **매핑 대상 평균 Sharpe의 부호**: `data/factor_weights.json`의 `meta.snapshot`에서 매핑 대상 6개(순유동성·VIX·MVRV·긴축환경÷2 두 개·과열회귀)의 Sharpe 평균을 직접 계산해 **양수인지 확인한다.** 음수면 `sharpe_i / mean(sharpe)`의 부호가 뒤집혀 가중치 순위가 통째로 역전된다(좋은 팩터 0.5, 나쁜 팩터 2.0). 경고 없이 조용히 일어나므로 반드시 수치로 확인할 것 — **음수면 채택 불가**, 산출식을 고치지 말고 여기서 종료한다
```

- [ ] **Step 3: 문서 수정 검증**

```bash
cd /e/Dev/coin
grep -c "매핑 대상 평균 Sharpe의 부호" docs/plans/spf-phase3-reweight-2026-08-23.md
grep -c "부호 역전" docs/plans/spf-phase3-reweight-2026-08-23.md
git diff --stat docs/plans/spf-phase3-reweight-2026-08-23.md
```

Expected:
- 첫 `grep -c` → `1`
- 둘째 `grep -c` → `1` 이상
- `git diff --stat` → `3 insertions(+)` (변경 파일은 이 md 하나뿐, 삭제 0줄). 본문 1줄 + 문단 구분용 빈 줄 1줄 + 체크리스트 1줄이다 — 마크다운에서 문단 앞뒤 빈 줄은 필수이므로 3줄이 정상이다. **`.py` 파일이 diff에 나오면 잘못한 것이다 — 되돌린다.**

- [ ] **Step 4: 커밋**

```bash
cd /e/Dev/coin
git add docs/plans/spf-phase3-reweight-2026-08-23.md
git commit -m "$(cat <<'EOF'
docs: SPF 3단계 채택 게이트에 평균 Sharpe 부호 확인 추가

derive_weights는 sharpe_i / mean(sharpe)로 나눈다. 2026-08-23 실측
스냅샷의 매핑 대상 평균은 +0.0842(합 +0.505)로 아슬아슬하게 양수라,
VIX Sharpe가 -3.45 부근까지만 더 나빠져도 평균이 음수가 된다. 그러면
나눗셈 부호가 뒤집혀 가중치 순위가 경고 없이 통째로 역전된다.
기존 계획서는 "0에 근접 → 클립 포화"만 경고했고 부호 역전은 언급이
없었다. 산출식은 그대로 두고 판정 체크리스트 항목만 추가한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `_curve_stats`에 `n_days_equity` 필드 추가 (TDD)

**Files:**
- Modify: `dashboard/backend/services/paper_engine.py` (`_curve_stats`, 200~221행)
- Test: `dashboard/tests/test_paper_engine.py` (기존 `test_curve_stats_mdd_and_total` 바로 아래, 현재 139행 뒤)

**TDD 규율:** Step 1~4 순서를 지킨다. **Step 2에서 실패를 눈으로 확인하기 전에 Step 3(구현)으로 가지 말 것.** 실패를 못 봤다면 그 테스트가 무엇을 검증하는지 알 수 없다.

- [ ] **Step 1: 실패하는 테스트 작성**

`dashboard/tests/test_paper_engine.py`의 `test_curve_stats_mdd_and_total`(현재 136~139행) 바로 아래, `def _two_days(...)` 헬퍼 정의 앞에 아래 2건을 추가한다. `_curve_stats`와 `pytest`는 파일 상단(7~18행)에서 이미 import돼 있으므로 **import는 추가하지 않는다.**

```python
def test_curve_stats_reports_equity_day_count():
    """리더보드 소비자(factor_weights.derive_weights)가 표본 가드에 쓰는 일수."""
    st = _curve_stats([100, 101, 99], [0.0, 0.01, -0.02], seed=100)
    assert st["n_days_equity"] == 3


def test_curve_stats_reports_zero_days_when_empty():
    """에쿼티 기록이 없으면 0 — 가드가 자동으로 걸러낸다."""
    st = _curve_stats([], [], seed=100)
    assert st["n_days_equity"] == 0
```

삽입 후 그 부분은 이렇게 보여야 한다:

```python
# ── 집계 (리더보드) ──────────────────────────────────────────
def test_curve_stats_mdd_and_total():
    st = _curve_stats([100, 110, 90, 120], [0.1, -0.18, 0.33], seed=100)
    assert st["total_return_pct"] == pytest.approx(20.0)
    assert st["mdd_pct"] == pytest.approx(-18.1818, abs=1e-3)  # 110→90


def test_curve_stats_reports_equity_day_count():
    """리더보드 소비자(factor_weights.derive_weights)가 표본 가드에 쓰는 일수."""
    st = _curve_stats([100, 101, 99], [0.0, 0.01, -0.02], seed=100)
    assert st["n_days_equity"] == 3


def test_curve_stats_reports_zero_days_when_empty():
    """에쿼티 기록이 없으면 0 — 가드가 자동으로 걸러낸다."""
    st = _curve_stats([], [], seed=100)
    assert st["n_days_equity"] == 0


def _two_days(indicator, z1, z2, p1, p2):
```

- [ ] **Step 2: 테스트 실패 확인 (건너뛰지 말 것)**

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests/test_paper_engine.py -q -k n_days_equity
```

Expected: **2 failed** — 두 건 모두 `KeyError: 'n_days_equity'`.

`-k n_days_equity`는 테스트 *이름*으로 거르는데 두 테스트 이름에 그 문자열이 없으므로 **0건 수집된다.** 실제로는 아래를 쓴다:

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests/test_paper_engine.py -q \
  -k "reports_equity_day_count or reports_zero_days_when_empty"
```

Expected: `2 failed`, 각각 `KeyError: 'n_days_equity'`. **`no tests ran`이 나오면 테스트를 잘못 붙인 것이므로 Step 1로 돌아간다.**

- [ ] **Step 3: 최소 구현**

`dashboard/backend/services/paper_engine.py`의 `_curve_stats`에서 **반환 dict 두 곳 모두**에 필드를 추가한다. 함수 안의 다른 줄(MDD 루프, Sharpe 계산)은 손대지 않는다.

빈 곡선 early return — 현재 203행:

```python
        return {"total_return_pct": 0.0, "mdd_pct": 0.0, "sharpe": 0.0, "equity": seed}
```

이렇게 바꾼다:

```python
        return {"total_return_pct": 0.0, "mdd_pct": 0.0, "sharpe": 0.0, "equity": seed,
                "n_days_equity": 0}
```

정상 반환 — 현재 216~221행:

```python
    return {
        "total_return_pct": (last / seed - 1) * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "equity": last,
    }
```

이렇게 바꾼다:

```python
    return {
        "total_return_pct": (last / seed - 1) * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "equity": last,
        "n_days_equity": len(equities),   # derive_weights 표본 가드용
    }
```

**두 곳 다 고쳐야 한다.** early return만 고치면 정상 경로 테스트가, 정상 반환만 고치면 빈 곡선 테스트가 계속 실패한다.

- [ ] **Step 4: 테스트 통과 + 회귀 확인**

먼저 새 테스트 2건:

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests/test_paper_engine.py -q \
  -k "reports_equity_day_count or reports_zero_days_when_empty"
```

Expected: `2 passed`.

이어서 대시보드 전체:

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

Expected: **실패 0건, 수집 220건.** 변경 전 기준선은 **218건**이므로 정확히 2건이 늘어야 한다.
(기준선 218은 2026-08-23에 `python -m pytest dashboard/tests -q --collect-only`로 실측한 값이다. 218이 아닌 다른 수에서 시작하면 그대로 기록하고, "시작 수 + 2"인지만 확인한다.)

프론트 회귀는 없다 — `/sim/leaderboard` 응답에 key가 하나 늘어날 뿐이고 프론트는 필요한 key만 읽는다. `leaderboard()`는 `_curve_stats` 결과 dict에 `st.update(...)`로 필드를 덧붙이는 구조(`paper_engine.py:256`)라 새 key가 그대로 응답에 실린다 — 의도한 동작이다.

- [ ] **Step 5: 커밋**

```bash
cd /e/Dev/coin
git add dashboard/backend/services/paper_engine.py dashboard/tests/test_paper_engine.py
git commit -m "$(cat <<'EOF'
feat: 리더보드 집계에 n_days_equity 추가 — 재가중 표본 가드 연결

derive_weights의 소표본 가드(에쿼티 관측 30일 미만이면 가중치 1.0)가
읽는 필드인데 생산자가 없어 KeyError가 났다. _curve_stats의 반환
경로 두 곳(빈 곡선·정상)에 관측일수를 넣는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: push (사용자 승인 완료) — 그리고 멈춤

상위 계획서 Task 2 Step 1이 요구하는 push다. `n_days_equity`가 프로덕션에 배포돼야 나중에 리더보드 스냅샷을 조회할 수 있다.

**Files:** 없음 (git 작업만)

- [ ] **Step 1: 올라갈 커밋 목록 확인**

```bash
cd /e/Dev/coin
git status --short
git log --oneline origin/master..HEAD
```

Expected `git log` 출력 — 아래 4개(위에서부터 최신순):

```
<신규>   feat: 리더보드 집계에 n_days_equity 추가 — 재가중 표본 가드 연결
<신규>   docs: SPF 3단계 채택 게이트에 평균 Sharpe 부호 확인 추가
7ece00d  docs: SPF 3단계 계획서 재작성 — 리더보드 forward 실측 기반으로 정정
6bc27a5  docs: SPF 3단계 재가중 구현 계획 작성
```

뒤 2개는 이번 작업 전부터 미푸시 상태였던 docs 커밋이다 — **정상이니 놀라지 말 것.**

Expected `git status --short`: 배경 절에 나열한 untracked 파일들만 `??`로 남아 있고, **staged/modified(`M`, `A`) 항목은 없어야 한다.** 뭔가 modified로 남아 있으면 커밋 누락이므로 멈추고 보고한다.

- [ ] **Step 2: push**

```bash
cd /e/Dev/coin
git push origin master
```

Expected: 4커밋 push 성공. Railway가 자동 배포를 시작한다.

- [ ] **Step 3: push 확인**

```bash
cd /e/Dev/coin
git fetch origin
git log --oneline origin/master -1
git log --oneline origin/master..HEAD
```

Expected: `origin/master`의 최신 커밋이 방금 만든 `feat: 리더보드 집계에 n_days_equity 추가...` 커밋이고, `origin/master..HEAD`는 **빈 출력**(로컬과 원격이 동일).

- [ ] **Step 4: 여기서 멈추고 보고**

**⛔ 상위 계획서 Task 2 Step 2(`railway ssh`로 프로덕션 리더보드 스냅샷 조회)부터는 진행하지 않는다.** 이번 범위가 끝났다. 아래를 보고하고 종료한다:

- 상위 계획서에 추가한 체크리스트 항목과 보강 문단 (해당 부분 diff)
- 추가한 테스트 2건과 `_curve_stats` 변경 내용
- `python -m pytest dashboard/tests -q` 최종 결과 (수집 수 218 → 220, 실패 0)
- push된 커밋 4개의 해시와 제목

배포 완료 확인, 스냅샷 조회, 가중치 산출, 백테스트 전후 비교, 프로덕션 배선은 **모두 다음 작업**이다. 시키지 않았는데 이어서 하지 말 것.

---

## 제약 (전 태스크 공통)

- **한국어** 주석·문서
- **TDD** — Task 2는 실패 테스트를 먼저 쓰고 실패를 눈으로 확인한 뒤 구현한다
- **외과적 변경** — 요청과 무관한 인접 코드·주석·포매팅·리팩터링에 손대지 않는다. 변경된 모든 줄이 이 계획의 특정 스텝으로 추적돼야 한다
- **새 패키지 설치 금지**
- 커밋 메시지는 `type: 한국어 설명` 형식 + 본문 마지막 줄에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` 트레일러
- **`git add`는 각 스텝에 명시된 경로만.** 저장소 루트에 untracked 파일이 다수 있으므로 **`git add .` / `git add -A` 절대 금지**
- `derive_weights`의 산출식(Sharpe 평균 나누기, 0.5~2.0 클립, 결합지표 분할)은 **고치지 않는다** — Task 1은 판정 체크리스트 항목 추가일 뿐이다
- `crypto-volatility-bot/app/macro/backtest_baseline.py`는 **건드리지 않는다** — 동등가중 베이스라인 경로가 유지돼야 앞으로의 전후 비교가 가능하다
- push는 Task 3 Step 2의 **한 번뿐**이다. 추가 push 금지

## Non-Goals

- 상위 계획서 Task 2 Step 2 이후 전부 (스냅샷 조회 · 가중치 산출 · 백테스트 전후 비교 · 채택 판정 · 프로덕션 배선)
- 브랜치 `spf-phase3-reweight`(커밋 `673a315`) 병합 — 별도 결정 사항
- `derive_weights` 산출식 개선 (클립 포화 · 거래 0건 표본 · 부호 역전 자체의 해결)
- 프론트엔드에서 `n_days_equity`를 노출·표시하는 작업 — 소비자는 봇 쪽 `derive_weights`뿐이다
- `leaderboard()` 레지스트리·은퇴 지표 정리
- Railway 배포 완료 확인 및 프로덕션 동작 검증

## Self-Review

- **범위 커버리지:** 확정 범위 3개(문서 게이트 보강 / `n_days_equity` 추가 / push)가 Task 1 / Task 2 / Task 3에 1:1 대응한다. "여기서 멈춤"은 Task 3 Step 4와 Non-Goals 양쪽에 명시했다.
- **플레이스홀더:** 없음. 문서 수정은 찾을 문자열·바꿀 문자열을 그대로 적었고, 코드 변경은 변경 전후 코드를 모두 실었으며, 모든 검증 스텝에 실행 명령과 기대 출력이 있다.
- **이름 일관성:** `n_days_equity`, `_curve_stats`, `derive_weights`, `dashboard/backend/services/paper_engine.py`, `dashboard/tests/test_paper_engine.py`, 테스트 함수명 `test_curve_stats_reports_equity_day_count` / `test_curve_stats_reports_zero_days_when_empty` — 전 태스크에서 동일하게 사용.
- **실측 확인:** `python -m pytest dashboard/tests -q --collect-only` = **218건**(2026-08-23 실측, 이 계획의 기준선). 앞서 언급된 348/574와 모순이 아니다 — 348은 봇 **`tests/unit`만**, 356은 봇 `tests` **전체**, 218은 대시보드이고 356 + 218 = 574로 맞는다(전부 브랜치 `spf-phase3-reweight` 워크트리 실측). 대시보드 218은 master와 워크트리가 동일하다.
- **함정 하나 명시:** Step 2의 `-k n_days_equity`는 테스트 *이름* 필터라 0건 수집된다. 상위 계획서에 그대로 적혀 있던 명령이므로 올바른 `-k` 표현식으로 교체하고 이유를 적었다.
