"""
logger.py — Structured logging with rotating file handler and coloured console output.

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Scrape cycle #42 completed")
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

# Try to import colorama for coloured output on Windows
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False


class ColouredFormatter(logging.Formatter):
    """Formatter that adds ANSI colour codes to console log output."""

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


def get_logger(name: str) -> logging.Logger:
    """
    Create and return a configured logger instance.

    - Rotating file handler  → logs/<name>.log  (plain text, no colours)
    - Console (stderr)       → coloured, human-readable
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called more than once
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False

    # ---------- File handler ----------
    log_file = LOG_DIR / "pipeline.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # ---------- Console handler ----------
    console_handler = logging.StreamHandler(sys.stderr)
    if _HAS_COLORAMA:
        console_fmt = ColouredFormatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        console_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger
