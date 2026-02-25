"""Structured logging helpers for orchestrator runtime."""

from __future__ import annotations

import logging
from pathlib import Path


def get_step_logger(log_path: Path) -> logging.Logger:
    """Return a step logger writing to ``log_path`` without duplicate handlers."""
    resolved_path = log_path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    logger_name = f"agentforge.step.{resolved_path.as_posix()}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler_path = Path(handler.baseFilename).resolve()
            if handler_path == resolved_path:
                return logger

    file_handler = logging.FileHandler(resolved_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    return logger
