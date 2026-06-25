"""
parser.py — Transforms raw scraped text into structured, typed data rows.

Takes the raw dict from scraper.read_snapshot() and produces a clean dict
that matches the Excel schema exactly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from config.settings import EXCEL_COLUMNS, VALID_SIGNALS
from utils.logger import get_logger

log = get_logger("parser")

# Regex to strip non-numeric chars from price, keeping digits, dots, commas
_PRICE_CLEAN_RE = re.compile(r"[^\d.,]")

# Known signal aliases (page sometimes uses slightly different text)
_SIGNAL_ALIASES = {
    "strong buy":  "Strong Buy",
    "buy":         "Buy",
    "neutral":     "Neutral",
    "sell":        "Sell",
    "strong sell": "Strong Sell",
    "n/a":         "N/A",
    "overbought":  "Sell",
    "oversold":    "Buy",
    "less volatility": "Neutral",
    "unlock":      "N/A",        # Locked behind paywall
    "":            "N/A",
}


def parse_price(raw_price: Optional[str]) -> Optional[float]:
    """
    Convert a price string like '4,127.33' or '4127.33' to a float.

    Returns None if the string cannot be parsed.
    """
    if not raw_price:
        return None
    try:
        cleaned = _PRICE_CLEAN_RE.sub("", raw_price)
        # Remove thousands separators (commas)
        cleaned = cleaned.replace(",", "")
        return float(cleaned)
    except (ValueError, TypeError) as e:
        log.warning(f"Could not parse price '{raw_price}': {e}")
        return None


def normalise_signal(raw_signal: Optional[str]) -> str:
    """
    Map raw signal text to one of the canonical signal values.

    Returns 'N/A' for unrecognised or missing inputs.
    """
    if not raw_signal:
        return "N/A"

    stripped = raw_signal.strip()
    # Try exact match (case-insensitive)
    normalised = _SIGNAL_ALIASES.get(stripped.lower())
    if normalised:
        return normalised

    # Check if any valid signal is a substring (for noisy text)
    for signal in ("Strong Buy", "Strong Sell", "Neutral", "Buy", "Sell"):
        if signal.lower() in stripped.lower():
            return signal

    log.warning(f"Unrecognised signal text: '{stripped}', defaulting to N/A")
    return "N/A"


def parse_snapshot(raw: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """
    Convert raw scraper output into a structured row dict.

    Input (from scraper.read_snapshot()):
        {
            "price": "4,127.33",
            "1 min": "N/A",
            "30 min": "Neutral",
            "Hourly": "Strong Sell",
            ...
        }

    Output:
        {
            "Date-Time": datetime(2026, 6, 23, 20, 35, 48),
            "Price": 4127.33,
            "1 min": "N/A",
            "5 min": "N/A",
            "30 min": "Neutral",
            "Hourly": "Strong Sell",
            ...
        }
    """
    row: Dict[str, Any] = {}

    # Timestamp (local time)
    row["Date-Time"] = datetime.now(timezone.utc)

    # Price
    row["Price"] = parse_price(raw.get("price"))

    # Timeframe signals
    for col in EXCEL_COLUMNS:
        if col in ("Date-Time", "Price"):
            continue
        row[col] = normalise_signal(raw.get(col))

    log.debug(
        f"Parsed row: price={row['Price']}, "
        f"signals=[{', '.join(row[c] for c in EXCEL_COLUMNS if c not in ('Date-Time', 'Price'))}]"
    )
    return row
