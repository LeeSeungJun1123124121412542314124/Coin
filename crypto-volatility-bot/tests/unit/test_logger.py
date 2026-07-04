"""Tests for app.utils.logger — JSON structured logging."""

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

from app.utils.logger import setup_logger


class TestSetupLogger:
    def test_returns_logger_instance(self):
        logger = setup_logger("test_returns")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        logger = setup_logger("my_logger")
        assert logger.name == "my_logger"

    def test_default_level_is_info(self):
        logger = setup_logger("test_level")
        assert logger.level == logging.INFO

    def test_custom_level(self):
        logger = setup_logger("test_debug", level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_json_output(self):
        stream = StringIO()
        logger = setup_logger("test_json", stream=stream)
        logger.info("hello world")
        output = stream.getvalue()
        data = json.loads(output.strip())
        assert "message" in data
        assert data["message"] == "hello world"

    def test_json_contains_level(self):
        stream = StringIO()
        logger = setup_logger("test_json_level", stream=stream)
        logger.warning("warn msg")
        output = stream.getvalue()
        data = json.loads(output.strip())
        # pythonjsonlogger uses 'levelname' field
        assert data.get("levelname") == "WARNING"


class TestAppNamespaceLogging:
    """모듈 로거(app.*)의 로그가 실제로 핸들러에 도달하는지 — 유실 방지."""

    def test_build_app_attaches_handler_to_app_namespace(self):
        """_build_app 후 'app' 로거에 핸들러가 있어야 모든 모듈 INFO가 관측됨."""
        cfg = MagicMock()
        cfg.log_level = "INFO"
        cfg.symbols = ["BTC/USDT"]
        app_logger = logging.getLogger("app")
        before = list(app_logger.handlers)
        try:
            app_logger.handlers.clear()
            with patch("app.main.Config") as mock_config, \
                 patch("app.main.NotificationDispatcher"), \
                 patch("app.main.create_app", return_value=MagicMock()):
                mock_config.from_env.return_value = cfg
                from app.main import _build_app
                _build_app()
            assert app_logger.handlers, "app 네임스페이스에 핸들러 없음 → 모듈 로그 전부 유실"
        finally:
            app_logger.handlers.clear()
            app_logger.handlers.extend(before)

    def test_module_logger_propagates_to_app_handler(self):
        """app.xxx 모듈 로거 INFO가 'app' 핸들러로 전파돼 JSON 출력됨."""
        stream = StringIO()
        setup_logger("app", stream=stream)
        try:
            logging.getLogger("app.pipeline_test_dummy").info("visible")
            data = json.loads(stream.getvalue().strip())
            assert data["message"] == "visible"
        finally:
            logging.getLogger("app").handlers.clear()
