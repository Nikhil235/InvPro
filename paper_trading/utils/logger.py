"""
logger.py -- Structured logging for the paper trading platform.

Writes to a separate log file (logs/paper_trading.log) with a [PAPER]
prefix so paper-trading events are clearly distinguished from pipeline logs.

Usage:
    from paper_trading.utils.logger import get_logger
    log = get_logger("broker")
    log.info("Order filled @ 3285.50")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Resolve paths relative to the InvPro project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOG_DIR / "paper_trading.log"
_LOG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
_LOG_BACKUP_COUNT = 5

# Try colorama for Windows console colours
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False


class _ColouredFormatter(logging.Formatter):
    """Formatter that adds ANSI colour codes for console output."""

    LEVEL_COLOURS = {
        logging.DEBUG:    Fore.CYAN    if _HAS_COLORAMA else "",
        logging.INFO:     Fore.GREEN   if _HAS_COLORAMA else "",
        logging.WARNING:  Fore.YELLOW  if _HAS_COLORAMA else "",
        logging.ERROR:    Fore.RED     if _HAS_COLORAMA else "",
        logging.CRITICAL: Fore.MAGENTA if _HAS_COLORAMA else "",
    }
    RESET = Style.RESET_ALL if _HAS_COLORAMA else ""

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, "")
        record.levelname = f"{colour}{record.levelname:<8}{self.RESET}"
        return super().format(record)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Create and return a logger for the paper trading subsystem.

    All loggers are prefixed with ``paper.`` to avoid collisions with
    the main pipeline's loggers.
    """
    qualified = f"paper.{name}"
    logger = logging.getLogger(qualified)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # ── File handler ──────────────────────────────────────────────
    fh = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | [PAPER] %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # ── Console handler ──────────────────────────────────────────
    ch = logging.StreamHandler(sys.stderr)
    if _HAS_COLORAMA:
        ch.setFormatter(_ColouredFormatter(
            "%(asctime)s | [PAPER] %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        ))
    else:
        ch.setFormatter(logging.Formatter(
            "%(asctime)s | [PAPER] %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        ))
    logger.addHandler(ch)

    return logger
