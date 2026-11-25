"""Logging setup. Logs go to a rotating file in the user's local app-data folder."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import log_dir  # noqa: F401  (re-exported: other modules import it from here)

LOGGER_NAME = "stofree"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if not name else f"{LOGGER_NAME}.{name}")


def setup_logging(level: int = logging.INFO, directory: Path | None = None) -> Path | None:
    """Configure the application logger; returns the log file path (or None)."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_stofree_configured", False):
        return getattr(logger, "_stofree_logfile", None)
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if sys.stderr is not None:           # windowed (console=False) frozen builds have no stderr
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    logfile: Path | None = None
    try:
        d = directory or log_dir()
        d.mkdir(parents=True, exist_ok=True)
        logfile = d / "stofree.log"
        fh = RotatingFileHandler(logfile, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        logger.warning("Could not create log file; logging to console only.")
        logfile = None
    logger._stofree_configured = True  # type: ignore[attr-defined]
    logger._stofree_logfile = logfile  # type: ignore[attr-defined]
    return logfile
