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
    assert "PRIMARY_TABS" in source
    assert "to={tab.path}" in source


def test_leaderboard_route_is_available_from_mobile_nav():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "import { Leaderboard }" in source
    assert "path: '/leaderboard'" in source
    assert '<Route path="/leaderboard" element={<Leaderboard />} />' in source


def test_mobile_shell_css_has_fixed_bottom_nav_and_safe_padding():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-bottom-nav" in source
    assert "position: fixed" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in source
    assert "@media (max-width: 760px)" in source
    assert "padding: 12px 10px 82px" in source


def test_desktop_shell_exposes_sidebar_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "mock-sidebar" in source
    assert "mock-brand" in source
    assert "mock-sidebar-link" in source
    assert 'aria-label="주요 화면"' in source


def test_desktop_shell_css_uses_sidebar_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-sidebar" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" in source
    assert "box-sizing: border-box" in source
    assert "height: calc(100vh - 52px)" in source
    assert ".mock-header-title" in source
    assert "display: none" in source


def test_desktop_shell_matches_mockup_geometry():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "min-height: 52px" in source
    assert "padding: 38px 12px 10px" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" in source
    assert "background: rgba(8, 15, 22, 0.96)" in source


def test_desktop_sidebar_matches_mockup_spacing():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "padding: 50px 10px 16px" in source
    assert "padding-left: 16px" in source
    assert "gap: 8px" in source
    assert "padding: 0 12px" in source
    assert "min-height: 38px" in source
