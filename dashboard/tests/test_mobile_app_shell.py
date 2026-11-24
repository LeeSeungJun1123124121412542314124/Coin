"""앱 셸 UI 계약 테스트 — 위쪽 메뉴·시세 띠·모바일 아래 탭 (docs/plans/light-redesign-spec-2026-11-24.md 5절)."""

from __future__ import annotations

import re
from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")
NAV_GROUPS_TS = Path("dashboard/frontend/src/lib/navGroups.ts")
TICKER_TSX = Path("dashboard/frontend/src/components/shared/TickerStrip.tsx")


def _css_block(source: str, selector: str) -> str:
    """`selector {` 로 시작하는 첫 CSS 블록 본문을 반환한다."""
    start = source.index(f"{selector} {{")
    return source[start:source.index("}", start)]


def test_app_shell_exposes_mobile_brand_and_group_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "투자분석기" in source
    assert "app-shell" in source
    assert "shell-brand-name" in source
    assert "shell-bottom" in source
    # 아래 탭은 묶음 5개의 짧은 이름 — 더보기 시트는 없다
    assert "{group.short}" in source
    assert "더보기" not in source
    assert "shell-sheet" not in source


def test_all_routes_are_reachable_from_group_navigation():
    source = APP_TSX.read_text(encoding="utf-8")
    nav_source = NAV_GROUPS_TS.read_text(encoding="utf-8")

    group_paths = re.findall(r"'(/[a-z-]*)'", nav_source)

    assert len(group_paths) == 12
    assert len(set(group_paths)) == 12
    # 묶음을 누르면 첫 화면으로, 묶음 안 나머지 화면은 그 아래 탭으로 간다
    assert "to={group.paths[0]}" in source
    assert "activeGroup.paths.map(path =>" in source
    assert "shell-subnav" in source
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
    # 먹색 바탕에 글자만 — 선택된 탭은 금색
    assert "background: var(--text)" in bottom_block
    assert "color: var(--gold-on-ink)" in _css_block(source, "  .shell-bottom-active")
    # 본문이 고정 하단 메뉴에 가려지지 않도록 하단 여백 확보
    assert "calc(64px + 16px + env(safe-area-inset-bottom))" in source
    # 모바일에서는 위쪽 묶음 메뉴를 숨기고 아래 탭을 쓴다
    mobile = source[source.index("  .shell-nav {", source.index(".shell-bottom {")):]
    assert "display: none" in mobile[:mobile.index("}")]


def test_desktop_shell_exposes_top_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "shell-masthead" in source
    assert "shell-brand" in source
    assert "shell-link" in source
    assert "NAV_GROUPS.map(group =>" in source
    assert "shell-sidebar" not in source
    assert "{tab.icon}" not in source
    assert 'aria-label="주요 화면"' in source


def test_desktop_shell_css_uses_top_navigation_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".shell-sidebar" not in source
    assert "grid-template-columns: 232px minmax(0, 1fr)" not in source
    masthead_block = _css_block(source, ".shell-masthead")
    assert "position: sticky" in masthead_block
    assert "border-bottom: 1px solid var(--text)" in masthead_block
    assert ".shell-subnav" in source
    assert ".shell-title" in source
    assert ".shell-updated" in source


def test_desktop_shell_matches_mockup_geometry():
    source = INDEX_CSS.read_text(encoding="utf-8")

    # .app-main 은 기본 규칙 뒤에서 셸 규칙이 덮어쓰므로 마지막 선언을 검사
    app_main = source[source.rindex("\n.app-main {"):]
    assert "padding: 36px 48px 56px" in app_main[:app_main.index("}")]
    assert "max-width: 1440px" in app_main[:app_main.index("}")]
    assert "margin-bottom: 24px" in _css_block(source, ".shell-page-head")
    app_shell = source[source.rindex("\n.app-shell {"):]
    assert "flex-direction: column" in app_shell[:app_shell.index("}")]


def test_top_navigation_marks_active_group_with_gold_underline():
    source = INDEX_CSS.read_text(encoding="utf-8")

    link_block = _css_block(source, ".shell-link")
    assert "min-height: 72px" in link_block
    assert "border-bottom: 3px solid transparent" in link_block
    assert "border-bottom-color: var(--gold)" in _css_block(source, ".shell-link-active")
    # 묶음 안 탭은 먹색 밑줄
    assert "border-bottom-color: var(--text)" in _css_block(source, ".shell-sublink-active")


def test_ticker_strip_shows_coin_changes_and_last_updated():
    app_source = APP_TSX.read_text(encoding="utf-8")
    ticker_source = TICKER_TSX.read_text(encoding="utf-8")
    css_source = INDEX_CSS.read_text(encoding="utf-8")

    # 시세 띠는 실제 코인 슬롯의 24시간 등락을 쓴다
    assert "useApi<TickerData>('/api/dashboard', 60_000)" in ticker_source
    assert "coin.change_24h" in ticker_source
    assert "<TickerStrip>" in app_source
    ticker_block = _css_block(css_source, ".shell-ticker")
    assert "background: var(--text)" in ticker_block
    assert "color: var(--up-on-ink)" in css_source
    assert "color: var(--down-on-ink)" in css_source


def test_header_uses_active_menu_metadata_without_static_dashboard_title():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "useLocation" in source
    assert "activeTab.label" in source
    assert "activeTab.description" in source
    assert "shell-title" in source
    # 홈은 판단 제목이 화면 제목을 대신한다
    assert "activeTab.path !== '/'" in source
    assert "실시간 시장 데이터 대시보드" not in source
    assert "최종 갱신" in source


def test_desktop_header_typography_emphasizes_brand_and_active_menu():
    source = INDEX_CSS.read_text(encoding="utf-8")

    brand_block = _css_block(source, ".shell-brand-name")
    title_block = _css_block(source, ".shell-title")

    assert "font-size: 22px" in brand_block
    assert "font-weight: 800" in brand_block
    assert "font-size: 34px" in title_block
    assert "font-weight: 800" in title_block


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
