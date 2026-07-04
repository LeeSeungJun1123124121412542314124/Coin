"""모바일 앱 셸 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_app_shell_exposes_mobile_brand_and_primary_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "투자분석기" in source
    assert "app-shell" in source
    assert "app-topbar" in source
    assert "app-brand-title" in source
    assert "app-bottom-nav" in source
    assert "PRIMARY_TABS" in source
    assert "to={tab.path}" in source


def test_leaderboard_route_is_available_from_mobile_nav():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "import { Leaderboard }" in source
    assert "path: '/leaderboard'" in source
    assert '<Route path="/leaderboard" element={<Leaderboard />} />' in source


def test_mobile_shell_css_has_fixed_bottom_nav_and_safe_padding():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".app-bottom-nav" in source
    assert "position: fixed" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in source
    assert "@media (max-width: 640px)" in source
    assert "padding-bottom: 86px" in source


def test_desktop_shell_exposes_sidebar_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "app-desktop-sidebar" in source
    assert "app-desktop-brand" in source
    assert "app-sidebar-link" in source
    assert 'aria-label="PC 주요 화면"' in source


def test_desktop_shell_css_uses_sidebar_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "@media (min-width: 900px)" in source
    assert ".app-desktop-sidebar" in source
    assert "width: 229px" in source
    assert "box-sizing: border-box" in source
    assert "left: 229px" in source
    assert "margin-left: 229px" in source
    assert ".app-tab-scroll" in source
    assert "display: none" in source


def test_desktop_shell_matches_mockup_geometry():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "min-height: 55px" in source
    assert "padding: 0 24px 0 28px" in source
    assert "padding: 74px 24px 28px 28px" in source
    assert "max-width: none" in source
    assert "background: #0f1724" in source
