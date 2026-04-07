"""Tests for app.utils.logger — JSON structured logging."""

import json
import logging
from io import StringIO

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
