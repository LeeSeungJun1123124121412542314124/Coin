"""크롬에서 '앱 설치'가 되도록 하는 파일들 (docs/plans/pwa-spec-2026-11-24.md)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

FRONTEND = Path("dashboard/frontend")
PUBLIC = FRONTEND / "public"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"PNG가 아님: {path}"
    return struct.unpack(">II", data[16:24])


def test_manifest_describes_installable_app() -> None:
    manifest = json.loads((PUBLIC / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["name"] == "투자분석기"
    assert manifest["short_name"] == "투자분석기"
    assert manifest["lang"] == "ko"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    # 앱 바탕(아이보리)과 맨 위 시세 띠(먹색)에 맞춘다 — 켜질 때 색이 튀지 않게
    assert manifest["background_color"] == "#F8F6F1"
    assert manifest["theme_color"] == "#25231F"
    assert [(i["src"], i["sizes"], i["purpose"]) for i in manifest["icons"]] == [
        ("/icons/icon-192.png", "192x192", "any"),
        ("/icons/icon-512.png", "512x512", "any"),
        ("/icons/maskable-512.png", "512x512", "maskable"),
    ]


@pytest.mark.parametrize("name, size", [
    ("icon-192.png", 192),
    ("icon-512.png", 512),
    ("maskable-512.png", 512),
    ("apple-touch-icon.png", 180),
])
def test_icon_files_have_the_declared_pixel_size(name: str, size: int) -> None:
    assert _png_size(PUBLIC / "icons" / name) == (size, size)


def test_icon_svg_uses_brand_mark() -> None:
    svg = (PUBLIC / "icons" / "icon.svg").read_text(encoding="utf-8")

    assert "#C8A86B" in svg          # 금색 바탕
    assert "M3 17l5-5 4 4 8-9" in svg  # 앱 머리의 차트 선과 같은 모양


def test_index_html_links_manifest_and_icons() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert '<link rel="manifest" href="/manifest.webmanifest" />' in html
    assert '<meta name="theme-color" content="#25231F" />' in html
    assert '<link rel="icon" href="/icons/icon.svg" type="image/svg+xml" />' in html
    assert '<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />' in html
    assert '<meta name="apple-mobile-web-app-title" content="투자분석기" />' in html
    # 기본 Vite 로고는 더 쓰지 않는다
    assert "favicon.svg" not in html


def test_service_worker_caches_shell_but_never_api() -> None:
    sw = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    assert 'req.mode === "navigate"' in sw
    assert 'path.startsWith("/api/")' in sw                      # API는 브라우저가 그대로 처리
    assert 'path.startsWith("/assets/") || path.startsWith("/icons/")' in sw
    assert "url.origin !== self.location.origin" in sw           # 다른 출처(글꼴 등)는 건드리지 않음
    assert 'req.method !== "GET"' in sw
    # 휴대폰 알림(웹 푸시)은 넣지 않았다
    assert '"push"' not in sw and "showNotification" not in sw


def test_main_registers_service_worker_only_in_production_build() -> None:
    main = (FRONTEND / "src" / "main.tsx").read_text(encoding="utf-8")

    assert 'navigator.serviceWorker.register("/sw.js")' in main
    assert "import.meta.env.PROD" in main
    # 개발 서버에서는 남아 있던 등록을 지운다(HMR과 섞이지 않게)
    assert "getRegistrations()" in main and "unregister()" in main


def test_server_serves_pwa_files_as_real_files(tmp_path) -> None:
    """빌드 결과에 들어간 파일은 index.html 폴백이 아니라 그 파일 자체가 나가야 한다."""
    from dashboard.backend.services.spa_files import safe_static_file

    dist = tmp_path / "dist"
    (dist / "icons").mkdir(parents=True)
    for rel in ("index.html", "manifest.webmanifest", "sw.js", "icons/icon-192.png"):
        (dist / rel).write_text("x", encoding="utf-8")

    for rel in ("manifest.webmanifest", "sw.js", "icons/icon-192.png"):
        assert safe_static_file(dist, rel) == (dist / rel).resolve()
    assert safe_static_file(dist, "research") is None  # 화면 경로는 index.html 폴백
