"""SPA catch-all 정적 파일 서빙 — 경로 탐색(path traversal) 방어 테스트.

main.py는 로컬 venv에 없는 slowapi를 임포트하므로 판정 함수(services.spa_files)만 단위 테스트.
"""
from __future__ import annotations

import pytest

from dashboard.backend.services.spa_files import safe_static_file


@pytest.fixture
def dist(tmp_path):
    """임시 dist 폴더 + dist 밖 비밀 파일."""
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html></html>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.env").write_text("SECRET=1", encoding="utf-8")
    return d


def test_serves_file_inside_dist(dist):
    assert safe_static_file(dist, "assets/app.js") == (dist / "assets" / "app.js").resolve()


def test_blocks_parent_traversal(dist):
    """상위 디렉터리 이동 시퀀스로 dist 밖 파일 접근 시 None (index.html 폴백)."""
    assert safe_static_file(dist, "../secret.env") is None
    assert safe_static_file(dist, "assets/../../secret.env") is None


def test_blocks_absolute_path(dist, tmp_path):
    assert safe_static_file(dist, str(tmp_path / "secret.env")) is None


def test_missing_file_returns_none(dist):
    assert safe_static_file(dist, "no-such-file.js") is None
