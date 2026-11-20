"""SPF 최근 예측 기록 다horizon 배지 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


SPF_TSX = Path("dashboard/frontend/src/components/screens/SPF.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def _source() -> str:
    return SPF_TSX.read_text(encoding="utf-8")


def _recent_history_section(source: str) -> str:
    start = source.index("최근 예측 기록")
    end = source.index("</Card>", start)
    return source[start:end]


def test_recent_prediction_history_uses_7_14_30_60_badges():
    source = _source()
    section = _recent_history_section(source)

    assert "판정: 7/14/30/60일" in section
    assert "HISTORY_HORIZONS.map" in section
    # 기간마다 기호만이 아니라 글자 라벨("✓ 적중")로 읽힌다
    assert "{meta.symbol} {meta.text}" in section
    assert "result_7d" in source
    assert "result_14d" in source
    assert "result_30d" in source
    assert "result_60d" in source


def test_recent_prediction_history_removes_legacy_3d_result_badge():
    section = _recent_history_section(_source())

    assert "p.result ===" not in section
    assert "✓ 적중" not in section
    assert "✗ 미스" not in section
    assert "판정중" not in section


def test_recent_prediction_history_states_do_not_wrap_mid_label_on_mobile():
    source = _source()
    section = _recent_history_section(source)
    css = INDEX_CSS.read_text(encoding="utf-8")

    # 데스크톱은 기간별 열이 있는 표, 모바일은 예측 하나당 4칸 블록 (둘 중 하나만 그린다)
    assert "useIsMobile()" in source
    assert "isMobile ?" in section
    assert "spf-log-cells" in section
    assert "spf-log-row" in section
    assert 'className="v2-nowrap"' in section
    # 라벨은 12px 이상 — 옛 9/11px 미니 배지는 없다
    assert "fontSize: 9" not in section
    assert "fontSize: 11" not in section
    cells_start = css.index(".spf-log-cells {")
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css[cells_start:css.index("}", cells_start)]


def test_recent_prediction_history_status_mapping_is_complete():
    source = _source()

    # 색상은 리디자인에서 hex 리터럴에서 theme 토큰(C.*)으로 이동함
    assert "'hit': { symbol: '✓', color: C.ok" in source
    assert "'miss': { symbol: '✗', color: C.warn" in source
    assert "'neutral': { symbol: '–', color: C.text2" in source
    assert "pending: { symbol: '·', color: C.text3" in source
    # 화면에 보이는 라벨
    for text in ("적중", "빗나감", "중립", "대기"):
        assert f"text: '{text}'" in source


def test_recent_prediction_history_unknown_status_falls_back_to_pending():
    source = _source()

    assert "function getHorizonResultMeta(result: string | null)" in source
    assert "result in HORIZON_RESULT_META" in source
    assert "return HORIZON_RESULT_META.pending" in source
