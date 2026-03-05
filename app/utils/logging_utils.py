from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import EMAIL_WORKER_LOG_PATH, LOG_ROTATION_BACKUP_DAYS, WEBHOOK_LOG_PATH


def _build_file_logger(name: str, log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=LOG_ROTATION_BACKUP_DAYS,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


def get_webhook_logger() -> logging.Logger:
    return _build_file_logger("provider_webhook", WEBHOOK_LOG_PATH)


def get_email_worker_logger() -> logging.Logger:
    return _build_file_logger("email_worker", EMAIL_WORKER_LOG_PATH)


def get_app_logger() -> logging.Logger:
    # Backward-compatible wrapper: main app logger is webhook logger.
    return get_webhook_logger()

