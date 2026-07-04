"""모바일 앱 셸 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_app_shell_exposes_mobile_brand_and_primary_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "투자분석기" in source
    assert "app-shell" in source
    assert "mock-top-ticker" in source
    assert "mock-brand-name" in source
    assert "mock-bottom-nav" in source
    assert "TABS.map(tab =>" in source
    assert "to={tab.path}" in source


def test_all_sidebar_routes_are_available_from_mobile_nav():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "import { Leaderboard }" in source
    assert '<Route path="/leaderboard" element={<Leaderboard />} />' in source
    assert "PRIMARY_TABS" not in source
    assert 'aria-label="모바일 전체 메뉴"' in source


def test_mobile_shell_css_has_fixed_bottom_nav_and_safe_padding():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-bottom-nav" in source
    assert "position: fixed" in source
    assert "overflow-x: auto" in source
    assert "grid-auto-columns: max-content" in source
    assert "@media (max-width: 760px)" in source
    assert "padding: 12px 10px 88px" in source


def test_desktop_shell_exposes_sidebar_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "mock-sidebar" in source
    assert "mock-brand" in source
    assert "mock-sidebar-link" in source
    assert "mock-brand-mark" not in source
    assert "{tab.icon}" not in source
    assert 'aria-label="주요 화면"' in source


def test_desktop_shell_css_uses_sidebar_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-sidebar" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" in source
    assert "box-sizing: border-box" in source
    assert "height: calc(100vh - 52px)" in source
    assert ".mock-header-title" in source
    assert ".mock-header-meta" in source


def test_desktop_shell_matches_mockup_geometry():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "min-height: 52px" in source
    assert "padding: 18px 18px 14px" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" in source
    assert "background: rgba(8, 15, 22, 0.96)" in source


def test_desktop_sidebar_matches_mockup_spacing():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "padding: 50px 8px 16px" in source
    assert "gap: 8px" in source
    assert "padding: 0 14px" in source
    assert "min-height: 38px" in source


def test_header_uses_active_menu_metadata_without_static_dashboard_title():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "useLocation" in source
    assert "activeTab.label" in source
    assert "activeTab.description" in source
    assert "실시간 시장 데이터 대시보드" not in source
    assert "마지막 업데이트 :" in source
