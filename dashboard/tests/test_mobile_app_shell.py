"""모바일 앱 셸 UI 계약 테스트."""

from __future__ import annotations

import re
from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")
NAV_GROUPS_TS = Path("dashboard/frontend/src/lib/navGroups.ts")


def _css_block(source: str, selector: str) -> str:
    """`selector {` 로 시작하는 첫 CSS 블록 본문을 반환한다."""
    start = source.index(f"{selector} {{")
    return source[start:source.index("}", start)]


def test_app_shell_exposes_mobile_brand_and_primary_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "투자분석기" in source
    assert "app-shell" in source
    assert "shell-brand-name" in source
    assert "shell-bottom" in source
    assert "MOBILE_PRIMARY.map(m =>" in source
    assert "to={m.path}" in source
    assert "더보기" in source


def test_all_sidebar_routes_are_available_from_mobile_nav():
    source = APP_TSX.read_text(encoding="utf-8")
    nav_source = NAV_GROUPS_TS.read_text(encoding="utf-8")

    groups_src = nav_source[nav_source.index("NAV_GROUPS"):nav_source.index("MOBILE_PRIMARY")]
    primary_src = nav_source[nav_source.index("MOBILE_PRIMARY"):nav_source.index("groupOf")]
    group_paths = re.findall(r"'(/[a-z]*)'", groups_src)
    primary_paths = set(re.findall(r"path: '(/[a-z]*)'", primary_src))

    assert len(group_paths) == 11
    assert primary_paths <= set(group_paths)
    # 하단 5칸 중 앞 4칸은 MOBILE_PRIMARY, 나머지 경로는 더보기 시트(NAV_GROUPS 기준)로 도달
    assert "group.paths.filter(path => !primaryPaths.includes(path))" in source
    assert 'aria-label="전체 메뉴"' in source
    for path in group_paths:
        route = '<Route path="/" element=' if path == "/" else f'<Route path="{path}" element='
        assert route in source
    assert "import { Leaderboard }" in source
    assert '<Route path="/leaderboard" element={<Leaderboard />} />' in source


def test_mobile_shell_css_has_fixed_bottom_nav_and_safe_padding():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".shell-bottom" in source
    assert "@media (max-width: 767px)" in source
    bottom_block = _css_block(source, "  .shell-bottom")
    assert "position: fixed" in bottom_block
    assert "bottom: 0" in bottom_block
    assert "padding-bottom: env(safe-area-inset-bottom)" in bottom_block
    assert "grid-template-columns: repeat(5, 1fr)" in bottom_block
    # 본문이 고정 하단 메뉴에 가려지지 않도록 하단 여백 확보
    assert "calc(64px + 16px + env(safe-area-inset-bottom))" in source


def test_desktop_shell_exposes_sidebar_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "shell-sidebar" in source
    assert "shell-brand" in source
    assert "shell-link" in source
    assert "NAV_GROUPS.map(group =>" in source
    assert "{tab.icon}" not in source
    assert 'aria-label="주요 화면"' in source


def test_desktop_shell_css_uses_sidebar_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".shell-sidebar" in source
    assert "grid-template-columns: 232px minmax(0, 1fr)" in source
    assert "grid-template-columns: 168px minmax(0, 1fr)" not in source
    sidebar_block = _css_block(source, ".shell-sidebar")
    assert "position: sticky" in sidebar_block
    assert "height: 100vh" in sidebar_block
    assert ".shell-title" in source
    assert ".shell-updated" in source


def test_desktop_shell_matches_mockup_geometry():
    source = INDEX_CSS.read_text(encoding="utf-8")

    # .app-main 은 기본 규칙 뒤에서 셸 규칙이 덮어쓰므로 마지막 선언을 검사
    app_main = source[source.rindex("\n.app-main {"):]
    assert "padding: 32px 40px 56px" in app_main[:app_main.index("}")]
    assert "margin-bottom: 24px" in _css_block(source, ".shell-page-head")
    app_shell = source[source.rindex("\n.app-shell {"):]
    assert "grid-template-columns: 232px minmax(0, 1fr)" in app_shell[:app_shell.index("}")]
    assert "background: var(--bg)" in _css_block(source, ".shell-sidebar")


def test_desktop_sidebar_matches_mockup_spacing():
    source = INDEX_CSS.read_text(encoding="utf-8")

    sidebar_block = _css_block(source, ".shell-sidebar")
    link_block = _css_block(source, ".shell-link")
    assert "padding: 20px 12px" in sidebar_block
    assert "gap: 20px" in sidebar_block
    assert "padding: 0 10px" in link_block
    assert "height: 40px" in link_block


def test_header_uses_active_menu_metadata_without_static_dashboard_title():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "useLocation" in source
    assert "activeTab.label" in source
    assert "activeTab.description" in source
    assert "groupOf(activeTab.path)" in source
    assert "shell-crumb" in source
    assert "shell-title" in source
    assert "실시간 시장 데이터 대시보드" not in source
    assert "최종 갱신" in source


def test_desktop_header_typography_emphasizes_brand_and_active_menu():
    source = INDEX_CSS.read_text(encoding="utf-8")

    brand_block = _css_block(source, ".shell-brand-name")
    title_block = _css_block(source, ".shell-title")
    crumb_block = _css_block(source, ".shell-crumb")

    assert "font-size: 16px" in brand_block
    assert "font-weight: 700" in brand_block
    assert "font-size: 30px" in title_block
    assert "font-size: 13px" in crumb_block


def test_header_receives_last_updated_from_screen_component():
    app_source = APP_TSX.read_text(encoding="utf-8")
    last_updated_source = Path("dashboard/frontend/src/components/shared/LastUpdated.tsx").read_text(encoding="utf-8")

    assert "dashboard:last-updated" in app_source
    assert "pageLastUpdated" in app_source
    assert "화면별 데이터 기준" not in app_source
    assert "new CustomEvent('dashboard:last-updated'" in last_updated_source
    assert "return null" in last_updated_source


def test_mobile_leaderboard_reset_button_sits_below_list():
    leaderboard_source = Path("dashboard/frontend/src/components/screens/Leaderboard.tsx").read_text(encoding="utf-8")
    css_source = INDEX_CSS.read_text(encoding="utf-8")

    # 리셋 버튼은 목록·상세 아래(맨 아래)에 있고 설명이 붙는다
    assert "leaderboard-reset-button" in leaderboard_source
    assert leaderboard_source.index("leaderboard-cards") < leaderboard_source.index("leaderboard-reset-button")
    assert "모든 지표의 성과 기록이 지워집니다." in leaderboard_source
    assert ".leaderboard-reset-button" in css_source
    reset_start = css_source.index(".leaderboard-reset-button {", css_source.index("@media (max-width: 767px)", css_source.index(".leaderboard-reset-button:disabled")))
    assert "min-height: 48px" in css_source[reset_start:css_source.index("}", reset_start)]
