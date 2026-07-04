"""Tests for the configurable logging setup (level, file, fallbacks)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.logging import _resolve_level, configure_logging, get_logger


def test_resolve_level_known_and_unknown() -> None:
    assert _resolve_level("debug") == logging.DEBUG
    assert _resolve_level("WARNING") == logging.WARNING
    # Unknown or blank names fall back to INFO instead of crashing.
    assert _resolve_level("nope") == logging.INFO
    assert _resolve_level("") == logging.INFO


def test_log_file_receives_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "logs" / "pulse.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()

    configure_logging()
    get_logger("test_logging").info("file_logging_works", answer=42)

    content = log_file.read_text(encoding="utf-8")
    assert "file_logging_works" in content
    assert "answer=42" in content


def test_level_filters_lower_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "pulse.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    get_settings.cache_clear()

    configure_logging()
    logger = get_logger("test_logging")
    logger.info("should_be_filtered")
    logger.warning("should_be_written")

    content = log_file.read_text(encoding="utf-8")
    assert "should_be_filtered" not in content
    assert "should_be_written" in content


def test_unwritable_log_file_keeps_app_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    # /proc is not writable: the file handler is skipped, console keeps working.
    monkeypatch.setenv("LOG_FILE", "/proc/nope/pulse.log")
    get_settings.cache_clear()

    configure_logging()
    get_logger("test_logging").info("console_still_works")
