from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_module_logger(
    name: str,
    log_file: str | Path,
    *,
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> logging.Logger:
    logger = logging.getLogger(name)
    path = Path(log_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if not logger.handlers:
        try:
            handler = RotatingFileHandler(
                path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
            logger.addHandler(handler)
        except OSError:
            pass
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
