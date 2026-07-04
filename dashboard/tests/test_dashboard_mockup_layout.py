"""대시보드 목업 반응형 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_dashboard_uses_mockup_card_layout_classes():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert 'className="dashboard-screen"' in source
    assert 'className="dashboard-hero-grid"' in source
    assert 'className="dashboard-secondary-grid"' in source
    assert "dashboard-market-card" in source
    assert "dashboard-card-title" in source
    assert "dashboard-main-value" in source
    assert "dashboard-sparkline" in source
    assert "dashboard-gauge-card" in source


def test_dashboard_css_matches_desktop_mockup_grid():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".dashboard-hero-grid" in source
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in source
    assert ".dashboard-market-card" in source
    assert "min-height: 220px" in source
    assert ".dashboard-sparkline" in source
    assert "height: 86px" in source
    assert ".dashboard-secondary-grid" in source
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in source


def test_dashboard_css_has_mobile_mockup_stack():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "@media (max-width: 640px)" in source
    assert ".dashboard-hero-grid" in source
    assert "grid-template-columns: 1fr" in source
    assert "min-height: 190px" in source
    assert ".dashboard-gauge-card" in source
