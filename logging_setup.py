# logging_setup.py
import logging
import os
import sys
from typing import Optional
from logging.handlers import RotatingFileHandler
from config import LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

LOG_FORMAT= "%(asctime)s %(levelname)s [%(process)d:%(threadName)s] %(name)s: %(message)s"

# ---------------------------------------------------------------------------

def _coerce_level(level) -> int:
    if isinstance(level, int):
        return level
    try:
        return int(str(level))
    except ValueError:
        return getattr(logging, str(level).upper(), logging.INFO)

def _ensure_log_path(path: str) -> None:
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        sys.exit(f"[logging_setup] Cannot create log directory '{directory}': {e}")

    if not os.access(directory, os.W_OK):
        sys.exit(f"[logging_setup] Log directory not writable: '{directory}'. "
                 "Fix permissions or change LOG_PATH in config.py")

    try:
        with open(path, "a", encoding="utf-8"):
            pass
    except Exception as e:
        sys.exit(f"[logging_setup] Cannot open log file '{path}' for append: {e}. "
                 "Fix permissions/SELinux or change LOG_PATH in config.py")

def setup_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name or "netbox_scanner")
    if logger.handlers:
        return logger

    level = _coerce_level(LOG_LEVEL)
    logger.setLevel(level)

    _ensure_log_path(LOG_PATH)

    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)

    logger.propagate = False

    for noisy in ("urllib3", "requests", "pynetbox"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    return logger
