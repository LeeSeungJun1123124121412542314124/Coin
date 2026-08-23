# SPF 3단계 — 리더보드 실측 기반 재가중 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 리더보드 forward 실측으로 9팩터 가중치를 산출하고, 8년 백테스트 전후 비교가 동등가중 이상일 때만 프로덕션에 반영한다.

**Architecture:** 계산부는 이미 브랜치 `spf-phase3-reweight`의 커밋 `673a315`에 다 있다 — 가중평균(`compute_composite(..., weights=)`), 산출(`derive_weights(스냅샷)`), 전후 비교 CLI(`composite_history.py --weights-json`). 이 계획은 **그 위에서 연결·실행·판정·배선만** 한다. 새 계산 로직을 만들지 않는다.

**Tech Stack:** Python 3.12 / pandas / pytest (봇 venv) / Railway CLI (프로덕션 스냅샷 조회)

---

## 배경

### 왜 백테스트로 가중치를 뽑지 않는가

`docs/SPEC_paper-trading-leaderboard.md`(2026-06-13) 목표 문단이 프로젝트 결정을 못 박아 뒀다:

> **전진(forward, OOS)** 검증한다. 과거 백테스트(**과최적화 위험**)와 달리, **미래 미관측 데이터**로 지표의 실전 쓸모를 증명한다.

따라서 **가중치는 리더보드 forward 실측에서만** 뽑는다. 8년 백테스트는 가중치 *결정*이 아니라 "이 가중치가 과거를 깨먹지 않는지" **확인용 가드**로만 쓴다. 원 계획서 [spf-phase2-3-calibration-reweight-2026-07-05.md](spf-phase2-3-calibration-reweight-2026-07-05.md)의 역할 분담과 동일하다.

### 이미 되어 있는 것 (커밋 `673a315`, 테스트 9건 포함 348개 통과)

| | 위치 |
|---|---|
| 가중평균 계산 | `app/macro/direction_composite.py` — `compute_composite(factor_inputs, weights=None)`, `latest_tilt(..., weights=)` |
| 리더보드 → 팩터 가중치 | `app/macro/factor_weights.py` — `derive_weights(스냅샷)` |
| 백테스트 전후 비교 | `scripts/composite_history.py --weights-json` — H7/14/30/60 동등가중 vs 재가중 적중률·IC 출력 |

`weights=None`이 동등가중이라 **기존 동작은 그대로**다. `backtest_baseline.build_history_frame`이 인자 없이 호출하므로 베이스라인 경로도 오염되지 않는다.

### 남은 것 3개 = 이 계획의 범위

1. `derive_weights`는 `row["n_days_equity"]`를 읽는데 `paper_engine.leaderboard()`가 그 필드를 **안 내보낸다**. 저장소 전체에 생산자가 없고 테스트 fixture에만 있다 → 지금 연결하면 `KeyError`.
2. **한 번도 실행한 적이 없다.** `tests/unit/fixtures/factor_weights.json`은 `{"weights": {"vix_level": 1.5}}` 더미다. 재가중이 동등가중보다 나은지 아직 아무도 모른다.
3. **프로덕션에 안 붙어 있다.** `weights=`를 넘기는 호출부가 0개다(`signals.py:43`, `collect_spf.py:158`, `notification_dispatcher.py:138`, `macro_health.py:51` 전부 인자 없음).

### ⚠️ 판정 시 반드시 볼 것 — 산출식이 포화될 가능성이 높다

2026-08-23 프로덕션 리더보드 실측(`railway ssh`로 조회):

| 지표 | Sharpe | 총수익% | 거래수 |
|---|---|---|---|
| MVRV | 2.910 | +95.4 | **0** |
| 복합방향 | 2.628 | +29.3 | 42 |
| 긴축환경 | 0.810 | +6.6 | 6 |
| 과열회귀 | 0.775 | +2.7 | 13 |
| 도미넌스 | -0.319 | -2.7 | 9 |
| 볼린저밴드 | -0.753 | -15.9 | 33 |
| 순유동성 | -1.043 | -17.3 | 9 |
| 유동성 | -1.848 | -19.6 | 6 |
| VIX | -2.947 | -63.2 | 24 |

`derive_weights`는 매핑된 팩터 Sharpe의 **평균으로 나눈다**. 위 값으로 매핑 대상(순유동성·VIX·MVRV·긴축환경÷2·과열회귀)의 평균을 내면 **약 0.084 — 0에 근접**한다. 그래서 `sharpe / mean_sharpe`가 전부 클립 경계(0.5 또는 2.0)로 포화되고 중간값이 나오지 않는다. 즉 실질적으로 **"Sharpe 양수면 2.0, 음수면 0.5"** 인 이진 규칙이 된다.

**평균이 0 근처라는 것은 "부호 역전" 위험도 함께 뜻한다.** 매핑 대상 6개의 Sharpe 합은 **+0.505**, 평균은 **+0.0842**로 아슬아슬하게 양수다(순유동성 -1.043 · VIX -2.947 · MVRV +2.910 · 긴축환경 0.810을 반으로 나눈 +0.405 두 개 · 과열회귀 +0.775). 평균이 **음수로 넘어가면 `sharpe_i / mean(sharpe)`의 부호가 뒤집혀 가중치 순위가 통째로 역전**된다 — 좋은 팩터가 0.5를, 나쁜 팩터가 2.0을 받는다. 예외도 경고도 없이 조용히 일어난다. VIX Sharpe가 지금의 **-2.947에서 -3.45 부근까지만 더 나빠져도** 합이 0을 넘는다. 클립 포화와는 별개의 문제이므로 Task 3에서 **평균의 부호를 수치로 직접 확인**한다.

또 **MVRV는 거래 0건**이다 — 6월부터 포지션 하나를 계속 들고 있어 일별 에쿼티 변동만으로 Sharpe 2.91이 나왔다. 표본이 사실상 1개인 포지션이 최대 가중치를 받는다.

**이 두 가지는 버그가 아니라 현재 산출식의 성질이다.** 그대로 두고 Task 3의 백테스트 가드로 판정한다 — 가드를 통과하지 못하면 채택하지 않으면 되고, 통과하더라도 위 사정을 알고 결정해야 한다. 산출식 자체를 바꾸는 것은 이 계획의 범위 밖이다(Non-Goals 참조).

---

## File Structure

| 파일 | 역할 | 변경 |
|---|---|---|
| `dashboard/backend/services/paper_engine.py` | 리더보드 집계. `_curve_stats`가 곡선 통계를 만든다 | 수정 (Task 1) |
| `dashboard/tests/test_paper_engine.py` | 리더보드 집계 테스트 | 수정 (Task 1) |
| `crypto-volatility-bot/data/leaderboard_snapshot.json` | **신규(산출물)** 프로덕션 실측 스냅샷 | Task 2가 생성 |
| `crypto-volatility-bot/data/factor_weights.json` | **신규(산출물)** 산출된 가중치 + 근거 | Task 2가 생성 |
| `crypto-volatility-bot/app/macro/direction_composite.py` | 프로덕션 가중치 상수·버전 태그 | 수정 (Task 4, 채택 시) |
| `crypto-volatility-bot/app/macro/signals.py` 외 3곳 | 프로덕션 호출부 배선 | 수정 (Task 4, 채택 시) |

**실행 환경 (중요)**

봇과 대시보드는 **같은 저장소의 다른 하위 디렉터리**이고 테스트 실행 방법이 다르다.

```bash
# 봇 테스트·스크립트 — cwd가 crypto-volatility-bot 이어야 app... 임포트됨
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -m pytest tests/unit -q

# 대시보드 테스트 — repo 루트에서 시스템 python (공용 venv엔 apscheduler 없음)
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

worktree에는 `.venv`가 없으므로(gitignore) 봇 쪽은 위 절대경로 python을 쓴다.

---

### Task 1: `n_days_equity` 필드 추가

`derive_weights`의 표본 가드(`n_days_equity < 30`)가 동작하려면 리더보드가 그 필드를 내보내야 한다.

**Files:**
- Modify: `dashboard/backend/services/paper_engine.py` (`_curve_stats`)
- Test: `dashboard/tests/test_paper_engine.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`dashboard/tests/test_paper_engine.py` 끝에 추가한다:

`_curve_stats`는 이 파일 상단(`test_paper_engine.py:9`)에서 이미 import돼 있으므로 그대로 쓴다. 기존 `test_curve_stats_mdd_and_total` 바로 아래에 추가한다:

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

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests/test_paper_engine.py -q -k n_days_equity
```

Expected: FAIL — `KeyError: 'n_days_equity'`

- [ ] **Step 3: 구현**

`dashboard/backend/services/paper_engine.py`의 `_curve_stats`에서 **두 곳**의 반환 dict에 필드를 추가한다.

빈 곡선 early return:
```python
    if not equities:
        return {"total_return_pct": 0.0, "mdd_pct": 0.0, "sharpe": 0.0, "equity": seed,
                "n_days_equity": 0}
```

정상 반환:
```python
    return {
        "total_return_pct": (last / seed - 1) * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "equity": last,
        "n_days_equity": len(equities),   # derive_weights 표본 가드용
    }
```

- [ ] **Step 4: 테스트 통과 + 회귀 확인**

```bash
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

Expected: 신규 2건 포함 전부 통과. `/sim/leaderboard` 응답에 필드가 하나 늘어나는 것뿐이라 프론트 회귀는 없다(프론트는 필요한 key만 읽음).

- [ ] **Step 5: 커밋**

```bash
git add dashboard/backend/services/paper_engine.py dashboard/tests/test_paper_engine.py
git commit -m "feat: 리더보드 집계에 n_days_equity 추가 — 재가중 표본 가드 연결"
```

---

### Task 2: 실측 스냅샷 → 가중치 산출 → 전후 비교 실행

**Files:**
- Create: `crypto-volatility-bot/data/leaderboard_snapshot.json`
- Create: `crypto-volatility-bot/data/factor_weights.json`

- [ ] **Step 1: Task 1을 프로덕션에 배포**

스냅샷은 프로덕션 DB에서만 나온다. `n_days_equity`가 배포돼야 조회할 수 있다.

```bash
git push origin master
```

Railway 자동 배포. 배포 완료까지 대기한다.

- [ ] **Step 2: 프로덕션 리더보드 스냅샷 조회**

`railway ssh`는 명령을 `sh -c`로 넘기면서 따옴표를 깨뜨리므로 base64로 감싼다(검증된 방법):

```bash
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

출력 JSON 배열을 `crypto-volatility-bot/data/leaderboard_snapshot.json`에 저장한다.

**확인:** 모든 행에 `n_days_equity`가 있고, 은퇴 지표(달러·금리·TGA·RSI·모멘텀30d)는 목록에 없어야 한다(`leaderboard()`가 현재 레지스트리만 반환).

- [ ] **Step 3: 가중치 산출**

```bash
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -c "
import json
from app.macro.factor_weights import derive_weights
snap = json.load(open('data/leaderboard_snapshot.json', encoding='utf-8'))
out = derive_weights(snap)
json.dump(out, open('data/factor_weights.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
for k, v in sorted(out['weights'].items(), key=lambda kv: -kv[1]):
    print(f'{k:<20} {v:.4f}')
"
```

Expected: 9팩터 전부 출력. 배경 절의 예측대로면 6개가 0.5/2.0 경계에 붙고 3개(`active_addr_13w`, `sma50_dist`, `momentum_30d`)가 1.0이다. **다른 양상이면 그대로 기록하고 보고한다.**

- [ ] **Step 4: 백테스트 전후 비교**

```bash
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe scripts/composite_history.py \
  --from-csv data/composite_sources.csv --weights-json data/factor_weights.json
```

Expected: 기존 베이스라인 표(7일 56.5 / 14일 58.6 / 30일 61.4 / 60일 64.5)에 이어 **"동등가중 vs 재가중 비교"** 표가 H7/14/30/60 적중률·IC로 출력된다.

**주의:** 베이스라인 표가 위 숫자와 다르면 `--from-csv` 경로나 소스 CSV가 바뀐 것이므로 멈추고 보고한다.

- [ ] **Step 5: 산출물 커밋**

```bash
git add crypto-volatility-bot/data/leaderboard_snapshot.json crypto-volatility-bot/data/factor_weights.json
git commit -m "chore: SPF 재가중 실측 스냅샷·산출 가중치 기록"
```

- [ ] **Step 6: 결과 보고 후 멈춤**

다음을 그대로 보고한다. 채택 여부는 사람이 판정한다:
- 스냅샷 원본 (지표별 Sharpe / n_days_equity / 거래수)
- 산출된 9팩터 가중치 — 클립 경계(0.5·2.0)에 몇 개가 붙었는지
- 전후 비교 표 4개 호라이즌 전부 (적중률과 IC 모두)

---

### Task 3: 채택 게이트 — 사람 판정 (코드 변경 없음)

**계획서 AC:** *"재가중 모델의 백테스트 7/14/30/60 적중률이 동등가중 이상"*

- [ ] **Step 1: 판정**

Task 2 Step 6의 수치로 결정한다. 아래를 함께 본다:

- **적중률**: 4개 호라이즌 중 하나라도 동등가중보다 낮으면 AC 미충족
- **IC**: 적중률이 같아도 IC가 낮아지면 신호 품질이 떨어진 것
- **클립 포화**: 6팩터가 전부 경계값이면 "Sharpe 부호"만 반영된 이진 가중치다. 그 정도 정보로 모델을 바꿀 값어치가 있는지 판단
- **MVRV 거래 0건**: 포지션 1개짜리 표본이 최대 가중치를 받는 구조를 수용할지
- **매핑 대상 평균 Sharpe의 부호**: `data/factor_weights.json`의 `meta.snapshot`에서 매핑 대상 6개(순유동성·VIX·MVRV·긴축환경÷2 두 개·과열회귀)의 Sharpe 평균을 직접 계산해 **양수인지 확인한다.** 음수면 `sharpe_i / mean(sharpe)`의 부호가 뒤집혀 가중치 순위가 통째로 역전된다(좋은 팩터 0.5, 나쁜 팩터 2.0). 경고 없이 조용히 일어나므로 반드시 수치로 확인할 것 — **음수면 채택 불가**, 산출식을 고치지 말고 여기서 종료한다

**채택하지 않는 경우:** Task 4를 진행하지 않는다. `data/factor_weights.json`과 비교 결과는 커밋된 채로 남기고, 판정 근거를 이 문서 하단에 기록한 뒤 종료한다. **이것도 유효한 결과다** — 원 계획서가 요구한 가드가 작동한 것이고, 10주 표본으로는 아직 이르다는 증거가 된다.

**채택하는 경우:** Task 4로 진행.

---

### Task 4: 프로덕션 배선 (채택 시에만)

**Files:**
- Modify: `crypto-volatility-bot/app/macro/direction_composite.py`
- Modify: `crypto-volatility-bot/app/macro/signals.py`
- Modify: `dashboard/backend/jobs/collect_spf.py`
- Modify: `crypto-volatility-bot/app/notification_dispatcher.py`
- Modify: `dashboard/backend/services/macro_health.py`
- Test: `crypto-volatility-bot/tests/unit/test_direction_composite.py`

- [ ] **Step 1: 가중치 상수와 버전 태그 추가**

`app/macro/direction_composite.py`의 `FACTORS` 리스트 바로 아래에 추가한다. 값은 Task 2 Step 3이 출력한 것을 그대로 적는다:

```python
# 복합 모델 버전 — 재가중은 forward 실측 검증을 리셋한다.
# v1(동등가중) 기간의 리더보드·SPF 적중률과 v2 이후를 섞어서 평가하지 말 것.
COMPOSITE_VERSION = "v2-leaderboard-2026-08-23"

# 프로덕션 팩터 가중치 — 리더보드 forward 실측 Sharpe 기반
# 산출 근거: data/leaderboard_snapshot.json, data/factor_weights.json
# weights=None(동등가중)은 백테스트 베이스라인 비교용으로 계속 유지된다.
FACTOR_WEIGHTS: dict[str, float] = {
    # Task 2 Step 3의 출력을 그대로 적는다
}
```

- [ ] **Step 2: 테스트 작성**

`crypto-volatility-bot/tests/unit/test_direction_composite.py`에 추가한다:

```python
def test_factor_weights_cover_all_factors():
    """가중치가 FACTORS를 전부 덮어야 한다 — 누락 팩터가 조용히 1.0이 되면 안 된다."""
    from app.macro.direction_composite import FACTORS, FACTOR_WEIGHTS

    assert set(FACTOR_WEIGHTS) == {name for name, _c, _s in FACTORS}


def test_weights_none_still_equal_weighted():
    """베이스라인 경로(weights=None)는 재가중 이후에도 동등가중이어야 한다."""
    import pandas as pd
    from app.macro.direction_composite import compute_composite

    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    rising = pd.Series(range(300), dtype="float64", index=idx)
    plain = compute_composite({"net_liquidity_13w": rising, "dxy_13w": rising})
    # 부호가 반대인 두 팩터를 동등가중하면 상쇄되어 0
    assert plain.dropna().abs().max() < 1e-9
```

- [ ] **Step 3: 호출부 4곳 배선**

각각 `weights=FACTOR_WEIGHTS`를 넘긴다. import 추가가 필요하면 기존 import 줄에 이름만 더한다.

`crypto-volatility-bot/app/macro/signals.py:43`:
```python
    return SignalContext(closes=closes, macro_z=macro_z,
                         composite=compute_composite(factors, weights=FACTOR_WEIGHTS))
```

`dashboard/backend/jobs/collect_spf.py:158`, `crypto-volatility-bot/app/notification_dispatcher.py:138`, `dashboard/backend/services/macro_health.py:51` — 셋 다 동일 패턴:
```python
        return latest_tilt(build_factors(**sources), weights=FACTOR_WEIGHTS)
```

**`app/macro/backtest_baseline.py:29`는 건드리지 않는다** — 인자 없이 호출해야 동등가중 베이스라인이 유지되고, 앞으로의 전후 비교가 계속 가능하다.

- [ ] **Step 4: 양쪽 테스트 전부 통과 확인**

```bash
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe -m pytest tests/unit -q
cd /e/Dev/coin
python -m pytest dashboard/tests -q
```

Expected: 둘 다 실패 0건.

- [ ] **Step 5: 베이스라인 무오염 확인**

```bash
cd crypto-volatility-bot
/e/Dev/coin/crypto-volatility-bot/.venv/Scripts/python.exe scripts/composite_history.py --from-csv data/composite_sources.csv
```

Expected: **7일 56.5 / 14일 58.6 / 30일 61.4 / 60일 64.5** 그대로. 달라졌다면 배선이 베이스라인 경로까지 오염시킨 것이므로 멈추고 보고한다.

- [ ] **Step 6: 커밋**

```bash
git add crypto-volatility-bot/app/macro/direction_composite.py crypto-volatility-bot/app/macro/signals.py crypto-volatility-bot/app/notification_dispatcher.py dashboard/backend/jobs/collect_spf.py dashboard/backend/services/macro_health.py crypto-volatility-bot/tests/unit/test_direction_composite.py
git commit -m "feat: 복합 방향 모델에 리더보드 실측 가중치 적용 (v2)"
```

- [ ] **Step 7: 전환 시점 기록**

이 문서 하단에 채택 판정 근거(전후 비교 수치)와 전환 날짜를 추가한다. 리더보드의 **복합방향 포트폴리오는 이 시점부터 다른 전략**이 되므로, 이후 성적을 v1 기간과 섞어서 해석하면 안 된다.

---

## 제약 (전 태스크 공통)

- 한국어 주석 · TDD(실패 테스트 먼저) · 외과적 변경
- **새 패키지 설치 금지**
- 커밋 메시지는 `type: 한국어 설명` + 본문 마지막 줄 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` 트레일러
- `git add`는 명시된 경로만 (저장소 루트에 untracked 파일 다수 — `git add .` 금지)
- **Task 2 Step 1의 push 외에 추가 push 금지.** Task 4 배포 시점은 사용자가 정한다
- `derive_weights`의 산출식(Sharpe 평균 나누기, 0.5~2.0 클립, 결합지표 분할)은 **고치지 않는다** — 판정 대상이지 수정 대상이 아니다

## Non-Goals

- `derive_weights` 산출식 개선(클립 포화·거래 0건 표본 문제) — 판정 결과를 보고 별도 결정
- 2단계 확률 보정 — 가중치 확정 후 별도 계획
- 은퇴 지표 포트폴리오 정리, 리더보드 레지스트리 변경
- 백테스트 데이터 갱신(현재 2026-07-10까지) — 8년 표본에서 6주는 결과를 바꾸지 않는다
- `predictions` 테이블에 모델 버전 컬럼 추가 — 버전은 코드 상수로만 기록

## Self-Review

- **범위 커버리지:** 남은 3개(필드 누락 / 미실행 / 미배선)가 각각 Task 1 / Task 2 / Task 4에 대응하고, 원 계획서 AC(전후 비교 가드)는 Task 2 Step 4 + Task 3 게이트가 담당한다. `673a315`가 이미 한 계산부는 다시 만들지 않는다.
- **플레이스홀더:** Task 4 Step 1의 가중치 값만 비워뒀다 — Task 2의 실행 결과라 사전에 알 수 없고, 채우는 출처를 명시했다.
- **이름 일관성:** `n_days_equity`, `derive_weights`, `FACTOR_WEIGHTS`, `COMPOSITE_VERSION`, `data/leaderboard_snapshot.json`, `data/factor_weights.json` — 전 태스크에서 동일하게 사용.

---

## 판정 결과 (2026-08-23) — **채택 불가. SPF 3단계 종료**

Task 3 채택 게이트를 실행했다. **AC 미충족**이므로 Task 4(프로덕션 배선)는 진행하지 않는다.

### 전후 비교 (8년 백테스트, 2017-12-02 ~ 2026-07-10, composite 유효 2880일)

| H | 동등가중 적중률 | 재가중 적중률 | Δ | 동등가중 IC | 재가중 IC | Δ |
|---|---|---|---|---|---|---|
| 7 | 56.5 | **55.6** | -0.9pp | 0.136 | **0.100** | -26% |
| 14 | 58.6 | **57.9** | -0.7pp | 0.194 | **0.156** | -20% |
| 30 | 61.4 | **60.2** | -1.2pp | 0.266 | **0.229** | -14% |
| 60 | 64.5 | **63.7** | -0.8pp | 0.306 | **0.294** | -4% |

AC는 "재가중의 7/14/30/60 적중률이 동등가중 이상"이다. **4개 전부 미달**이고 IC도 4개 전부 열세다. 8개 칸 중 개선된 칸이 하나도 없다.

### 판정 체크리스트 5항목

| 항목 | 결과 |
|---|---|
| 적중률 | 4/4 미달 → **AC 미충족** |
| IC | 4/4 열세, 단기일수록 열화 큼(H7 -26%) |
| 클립 포화 | **6/9**가 경계값 — 예측대로 "Sharpe 부호만 반영된 이진 가중치" |
| MVRV 거래 0건 | `mvrv_level`이 **최대 가중치 2.0**. 71일간 포지션 1개를 보유한 표본으로 얻은 Sharpe 2.811이 1위 |
| **매핑 평균 Sharpe 부호** | **+0.036755** (합 +0.2205 / 6개) — 양수라 역전은 면했으나 0에 매우 근접 |

### 실측 스냅샷 (`data/leaderboard_snapshot.json`)

| 지표 | Sharpe | n_days_equity | 거래수 | 총수익% |
|---|---|---|---|---|
| MVRV | 2.811 | 71 | 0 | +91.4 |
| 복합방향 | 2.182 | 71 | 42 | +24.1 |
| 긴축환경 | 0.802 | 50 | 6 | +6.6 |
| 과열회귀 | 0.006 | 50 | 13 | -0.4 |
| 볼린저밴드 | -0.237 | 71 | 33 | -9.1 |
| 도미넌스 | -0.445 | 71 | 9 | -3.5 |
| 순유동성 | -0.866 | 71 | 9 | -15.3 |
| 유동성 | -1.612 | 50 | 6 | -17.9 |
| VIX | -2.531 | 71 | 24 | -59.6 |

산출 가중치(`data/factor_weights.json`): `dxy_13w`·`ust10y_13w`·`mvrv_level` = 2.0 / `net_liquidity_13w`·`vix_level`·`rsi14` = 0.5 / `active_addr_13w`·`sma50_dist`·`momentum_30d` = 1.0.

### 이 문서 본문의 예측과 어긋난 점

배경 절 "⚠️ 판정 시 반드시 볼 것"의 Sharpe 표는 같은 날 조회분인데도 실측과 달랐다. **과열회귀가 0.775 → 0.006으로 붕괴**했고, 그 결과 `rsi14` 가중치가 예측 2.0이 아니라 **0.5로 뒤집혔다.** 매핑 평균도 예측 +0.0842의 절반 이하인 +0.0368이었다. 10주 표본의 Sharpe가 하루 안에도 이만큼 움직인다는 것 자체가 아래 결론을 뒷받침한다.

### 결론

가중치가 **신호가 아니라 단기 노이즈를 인코딩**했다. 근거는 셋이다.

1. 경계 포화 6/9로 사실상 부호만 남은 이진 규칙이 됐다
2. 최대 가중치를 받은 팩터의 표본이 포지션 1개다
3. 같은 날 안에서도 순위가 뒤집힐 만큼 Sharpe가 불안정하다

8년 백테스트가 이를 8/8 열세로 확인했다. **원 계획서가 요구한 가드가 정확히 의도대로 작동한 것이고, 10주 forward 표본으로 9팩터를 재가중하기에는 아직 이르다는 증거다.**

### 남기는 것 / 남기지 않는 것

- **유지:** `compute_composite(..., weights=)` 가중평균 경로, `derive_weights`, `--weights-json` 비교 CLI, `n_days_equity` 필드. 전부 하위호환이라 프로덕션 동작은 동등가중 그대로다
- **하지 않음:** `FACTOR_WEIGHTS` 상수 추가, `COMPOSITE_VERSION` 태깅, 호출부 4곳 배선
- **재개 조건:** forward 표본이 충분히 쌓인 뒤(결합 지표 기준 최소 6개월, 즉 2027-01 이후) 같은 절차를 재실행한다. 재실행 시 이 문서의 Task 2~3을 그대로 쓰면 된다
- **별도 결정 대상:** 산출식 개선(클립 포화·거래 0건 표본·부호 역전). 여전히 Non-Goals이며, 재가중 자체를 다시 시도할 때 함께 판단한다
