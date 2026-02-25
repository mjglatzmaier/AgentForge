from pathlib import Path

from agentforge.utils.logging import get_step_logger


def _flush_handlers(logger_name: str) -> None:
    import logging

    logger = logging.getLogger(logger_name)
    for handler in logger.handlers:
        handler.flush()


def test_get_step_logger_writes_to_correct_file(tmp_path: Path) -> None:
    log_path = tmp_path / "steps" / "00_fetch" / "logs" / "step.log"
    logger = get_step_logger(log_path)

    logger.info("hello-step-log")
    _flush_handlers(logger.name)

    text = log_path.read_text(encoding="utf-8")
    assert "hello-step-log" in text


def test_get_step_logger_repeated_creation_avoids_duplicate_entries(tmp_path: Path) -> None:
    log_path = tmp_path / "steps" / "01_rank" / "logs" / "step.log"
    logger_a = get_step_logger(log_path)
    logger_b = get_step_logger(log_path)

    logger_a.info("single-entry")
    _flush_handlers(logger_a.name)

    text = log_path.read_text(encoding="utf-8")
    assert logger_a is logger_b
    assert text.count("single-entry") == 1
