"""SPF 최근 예측 기록 다horizon 배지 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


SPF_TSX = Path("dashboard/frontend/src/components/screens/SPF.tsx")


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


def test_recent_prediction_history_badges_wrap_as_group_on_mobile():
    section = _recent_history_section(_source())

    assert "flexWrap: 'wrap'" in section
    assert "gap: '4px 8px'" in section
    assert "display: 'inline-flex'" in section
    assert "minWidth: 26" in section
    assert "fontSize: 9" in section
    assert "fontSize: 11" in section


def test_recent_prediction_history_status_mapping_is_complete():
    source = _source()

    # 색상은 리디자인에서 hex 리터럴에서 theme 토큰(C.*)으로 이동함
    assert "'hit': { symbol: '✓', color: C.ok" in source
    assert "'miss': { symbol: '✗', color: C.warn" in source
    assert "'neutral': { symbol: '–', color: C.text2" in source
    assert "pending: { symbol: '·', color: C.text3" in source


def test_recent_prediction_history_unknown_status_falls_back_to_pending():
    source = _source()

    assert "function getHorizonResultMeta(result: string | null)" in source
    assert "result in HORIZON_RESULT_META" in source
    assert "return HORIZON_RESULT_META.pending" in source
