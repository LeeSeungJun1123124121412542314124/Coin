"""테스트 격리 검증 — 테스트 실행 중 실제 텔레그램 발송이 불가능해야 한다.

main.py 임포트는 app.utils.config의 load_dotenv()를 통해 .env의 실제
TELEGRAM_BOT_TOKEN/CHAT_ID를 환경변수로 로드한다. conftest가 이를 선점하지
않으면 잡 실패 경로를 검증하는 테스트가 진짜 알림을 발송한다 (2026-07-11 발생).
"""

from __future__ import annotations

import os


def test_telegram_credentials_are_isolated_even_after_main_import() -> None:
    # main 임포트 = load_dotenv() 실행 경로 (실제 사고 재현 경로)
    import dashboard.backend.main  # noqa: F401
    from dashboard.backend.utils import alerting

    assert os.getenv("TELEGRAM_BOT_TOKEN") == ""
    assert os.getenv("TELEGRAM_CHAT_ID") == ""
    assert alerting._TELEGRAM_TOKEN == ""
    assert alerting._CHAT_ID == ""
