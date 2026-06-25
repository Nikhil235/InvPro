"""
settings.py -- Configuration for the paper trading simulation platform.

All tunable parameters for the simulated broker, risk manager, and journal.
Values can be overridden via environment variables (same .env as the parent project).

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loading (reuse parent project's .env if present)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    return float(val) if val is not None else default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val is not None else default


def _env_str(key: str, default: str) -> str:
    val = os.environ.get(key)
    return val.strip() if val is not None else default


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PAPER_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PAPER_ROOT.parent
OUTPUT_DIR = PAPER_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Historical data directory (existing pipeline output)
DATA_DIR = PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Simulated Broker
# ---------------------------------------------------------------------------
INITIAL_CAPITAL      = _env_float("PT_INITIAL_CAPITAL", 10_000.0)
SPREAD_POINTS        = _env_float("PT_SPREAD_POINTS", 0.35)
SLIPPAGE_POINTS      = _env_float("PT_SLIPPAGE_POINTS", 0.10)
COMMISSION_PER_LOT   = _env_float("PT_COMMISSION_PER_LOT", 7.00)   # Round-trip
FILL_DELAY_SECONDS   = _env_int("PT_FILL_DELAY_SECONDS", 0)
LOT_SIZE             = _env_int("PT_LOT_SIZE", 100)                 # 1 lot = 100 oz XAU

# ---------------------------------------------------------------------------
# Risk Management
# ---------------------------------------------------------------------------
MAX_DAILY_LOSS_PCT   = _env_float("PT_MAX_DAILY_LOSS_PCT", 0.03)   # 3 % of capital
MAX_DAILY_TRADES     = _env_int("PT_MAX_DAILY_TRADES", 10)
MAX_OPEN_POSITIONS   = _env_int("PT_MAX_OPEN_POSITIONS", 2)
MIN_CONFIDENCE       = _env_str("PT_MIN_CONFIDENCE", "MEDIUM")     # LOW, MEDIUM, HIGH
MIN_REWARD_RISK      = _env_float("PT_MIN_REWARD_RISK", 2.0)       # 1:2 minimum

# Confidence ranking for comparison
CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# ---------------------------------------------------------------------------
# Journal & Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = _env_str("PT_LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Warning Banner
# ---------------------------------------------------------------------------
BANNER = """
================================================================================
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║   PAPER TRADING ONLY. NO LIVE EXECUTION. ALL RESULTS ARE SIMULATED.   ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  XAU/USD Paper Trading Platform
  Simulation Engine v1.0

  Capital:   ${capital:>12,.2f}
  Spread:    {spread:>12.2f} pts
  Slippage:  {slippage:>12.2f} pts
  Commission:${commission:>11.2f} / lot (round-trip)
  Max Daily Loss: {max_loss:>6.1f}%
  Max Trades/Day: {max_trades:>6d}
  Max Open Pos:   {max_pos:>6d}
================================================================================
"""


def print_banner() -> None:
    """Print the startup warning banner with current settings."""
    print(BANNER.format(
        capital=INITIAL_CAPITAL,
        spread=SPREAD_POINTS,
        slippage=SLIPPAGE_POINTS,
        commission=COMMISSION_PER_LOT,
        max_loss=MAX_DAILY_LOSS_PCT * 100,
        max_trades=MAX_DAILY_TRADES,
        max_pos=MAX_OPEN_POSITIONS,
    ))
