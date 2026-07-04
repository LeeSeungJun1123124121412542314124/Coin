"""대시보드 목업 반응형 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_dashboard_uses_mockup_card_layout_classes():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "mock-spf-dashboard" in source
    assert "mock-real-stack" in source
    assert "mock-market-overview" in source
    assert "mock-news-section" in source
    assert "mock-coin-price-section" in source
    assert "mock-kr-stock-section" in source
    assert "mock-market-detail-section" in source


def test_dashboard_css_matches_desktop_mockup_grid():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr 1.35fr" in source
    assert ".mock-spf-hero" in source
    assert "min-height: 266px" in source
    assert ".mock-main-chart" in source
    assert "height: 226px" in source
    assert ".mock-horizon-grid" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in source


def test_dashboard_css_has_mobile_mockup_stack():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "@media (max-width: 760px)" in source
    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr" in source
    assert ".mock-bottom-nav" in source
    assert ".mock-spf-hero" in source
