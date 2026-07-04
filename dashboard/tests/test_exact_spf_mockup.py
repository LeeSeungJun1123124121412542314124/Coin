"""SPF 목업 화면 구조 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_app_shell_uses_mockup_ticker_and_sidebar():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "mock-top-ticker" in source
    assert "mock-brand-mark" in source
    assert "mock-sidebar" in source
    assert "mock-sidebar-link" in source
    assert "API 연동" in source
    assert "기본 계정" in source


def test_dashboard_uses_exact_spf_mockup_sections():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "mock-spf-dashboard" in source
    assert "시장 방향 전망" in source
    assert "mock-spf-hero" in source
    assert "mock-horizon-grid" in source
    assert "mock-metric-grid" in source
    assert "SPF 추이" in source
    assert "최근 예측 기록" in source
    assert "시뮬레이터" in source
    assert "리더보드" in source


def test_css_contains_mockup_desktop_and_mobile_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-top-ticker" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" in source
    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr 1.35fr" in source
    assert ".mock-spf-hero" in source
    assert ".mock-bottom-nav" in source
    assert "@media (max-width: 760px)" in source
