"""
settings.py — Central configuration for the XAU/USD Gold Trading Data Pipeline.

All tunable parameters are defined here. Modify this file to change
scraping intervals, file paths, validation thresholds, browser settings,
and strategy parameters.

Environment variables from a `.env` file (if present) override the
defaults defined below.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env file loading (optional — defaults used when .env is absent)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv not installed — use defaults only

def _env_float(key: str, default: float) -> float:
    """Read a float from the environment, falling back to *default*."""
    val = os.environ.get(key)
    return float(val) if val is not None else default

def _env_int(key: str, default: int) -> int:
    """Read an int from the environment, falling back to *default*."""
    val = os.environ.get(key)
    return int(val) if val is not None else default

def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean from the environment ('true'/'1' → True)."""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")

def _env_str(key: str, default: str) -> str:
    """Read a string from the environment, falling back to *default*."""
    val = os.environ.get(key)
    return val.strip() if val is not None else default

# ---------------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SESSION_DIR = PROJECT_ROOT / "session"   # Persistent browser state (cookies, localStorage)
HEALTH_FILE = PROJECT_ROOT / "health.json"

# Ensure output directories exist on import
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Target URL
# ---------------------------------------------------------------------------
TARGET_URL = "https://www.investing.com/currencies/xau-usd-technical"
SIGNIN_URL = "https://www.investing.com/"
SIGNIN_TIMEOUT_SECONDS = 120       # Max time to wait for user to complete sign-in

# ---------------------------------------------------------------------------
# Scraping & Scheduling
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_SECONDS = _env_int("REFRESH_INTERVAL_SECONDS", 5)
PAGE_LOAD_TIMEOUT_MS = 20_000      # Max wait for initial page load
ELEMENT_TIMEOUT_MS = 10_000        # Max wait for individual DOM elements
MAX_RETRIES = 3                    # Retries per scrape cycle on failure
RETRY_BASE_DELAY_SECONDS = 2      # Base delay for exponential backoff
BROWSER_REFRESH_EVERY_N_CYCLES = 500  # Full page reload interval (memory mgmt)
WATCHDOG_TIMEOUT_SECONDS = 120     # Auto-restart browser if no success in N sec

# ---------------------------------------------------------------------------
# Browser Settings
# ---------------------------------------------------------------------------
HEADLESS = _env_bool("HEADLESS", True)
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-infobars",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1920, "height": 1080}

# ---------------------------------------------------------------------------
# Excel Schema — Raw Data Columns
# ---------------------------------------------------------------------------
EXCEL_COLUMNS = [
    "Date-Time",
    "Price",
    "1 min",
    "5 min",
    "15 min",
    "30 min",
    "Hourly",
    "5 Hours",
    "Daily",
    "Weekly",
    "Monthly",
]

# ---------------------------------------------------------------------------
# Excel Schema — Strategy Output Columns (appended after raw data)
# ---------------------------------------------------------------------------
STRATEGY_COLUMNS = [
    "Signal",            # LONG / SHORT / FLAT
    "Bias",              # e.g. "Bullish (Daily=Buy, Weekly=Strong Buy)"
    "Confidence",        # HIGH / MEDIUM / LOW
    "Entry",             # Entry price
    "Stop Loss",         # Computed SL
    "Take Profit",       # Computed TP
    "Risk ($)",          # Dollar risk for this trade
    "Position (lots)",   # Lot size
    "Reason",            # Human-readable decision rationale
]

# Combined column list for the full Excel header
ALL_EXCEL_COLUMNS = EXCEL_COLUMNS + STRATEGY_COLUMNS

# Timeframes we attempt to scrape (in the order they appear on the page)
# Each entry: (tab_label_on_page, column_name_in_excel)
TIMEFRAME_MAP = [
    ("1 Min",    "1 min"),
    ("5 Min",    "5 min"),
    ("15 Min",   "15 min"),
    ("30 Min",   "30 min"),
    ("Hourly",   "Hourly"),
    ("5 Hours",  "5 Hours"),
    ("Daily",    "Daily"),
    ("Weekly",   "Weekly"),
    ("Monthly",  "Monthly"),
]

# InvestingPro subscription active -- all timeframes unlocked
LOCKED_TIMEFRAMES = set()  # Empty = all timeframes accessible

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
VALID_SIGNALS = {"Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell", "N/A"}
PRICE_MIN = 500.0       # Minimum plausible XAU/USD price
PRICE_MAX = 15000.0     # Maximum plausible XAU/USD price
STALENESS_THRESHOLD = 20  # Flag stale if price unchanged for N consecutive reads

# ---------------------------------------------------------------------------
# Strategy (Rule-Based Trading)
# ---------------------------------------------------------------------------
ACCOUNT_BALANCE       = _env_float("ACCOUNT_BALANCE", 10_000.0)
RISK_PER_TRADE_PCT    = _env_float("RISK_PER_TRADE_PCT", 0.01)   # 1 %
MIN_REWARD_RISK_RATIO = _env_float("MIN_REWARD_RISK_RATIO", 2.0) # 1:2
ATR_PERIOD            = _env_int("ATR_PERIOD", 14)
ATR_STOP_MULTIPLIER   = _env_float("ATR_STOP_MULTIPLIER", 1.5)
LOT_SIZE              = _env_int("LOT_SIZE", 100)                # 1 lot = 100 oz XAU
STRATEGY_EVAL_INTERVAL = _env_int("STRATEGY_EVAL_INTERVAL", 30)  # Evaluate every N cycles

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per log file
LOG_BACKUP_COUNT = 5               # Keep 5 rotated log files

# ---------------------------------------------------------------------------
# Excel File Naming
# ---------------------------------------------------------------------------
EXCEL_FILE_PREFIX = "xau_usd_"
EXCEL_FILE_EXTENSION = ".xlsx"

def get_excel_filename(date_str: str) -> Path:
    """Return the Excel file path for a given date string (YYYY-MM-DD)."""
    return DATA_DIR / f"{EXCEL_FILE_PREFIX}{date_str}{EXCEL_FILE_EXTENSION}"
