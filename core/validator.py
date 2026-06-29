"""
validator.py — Data quality checks before writing to Excel.

Validates price range, signal values, detects duplicates,
and flags stale data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from config.settings import (
    EXCEL_COLUMNS,
    VALID_SIGNALS,
    PRICE_MIN,
    PRICE_MAX,
    STALENESS_THRESHOLD,
)
from utils.logger import get_logger

log = get_logger("validator")


class DataValidator:
    """
    Stateful validator that tracks consecutive identical prices
    to detect stale data feeds.
    """

    def __init__(self) -> None:
        self._last_price: Optional[float] = None
        self._last_signals: Optional[Dict[str, str]] = None
        self._consecutive_same_price: int = 0

    def validate(self, row: Dict[str, Any]) -> tuple[bool, str, Dict[str, str]]:
        """
        Validate a parsed data row.

        Returns:
            (is_valid, reason, corrections) — True if the row should be stored,
            False with a human-readable reason to skip.  ``corrections`` is a
            dict of ``{column: corrected_value}`` that the caller should apply
            to the row before storage (the validator does NOT mutate the input).
        """
        corrections: Dict[str, str] = {}
        price = row.get("Price")

        # ----- Check 1: Price must be present -----
        if price is None:
            return False, "Price is missing or could not be parsed", corrections

        # ----- Check 2: Price must be in plausible range -----
        if not (PRICE_MIN <= price <= PRICE_MAX):
            return False, f"Price {price} outside plausible range [{PRICE_MIN}, {PRICE_MAX}]", corrections

        # ----- Check 3: Signal values must be valid -----
        for col in EXCEL_COLUMNS:
            if col in ("Date-Time", "Price"):
                continue
            signal = row.get(col, "N/A")
            if signal not in VALID_SIGNALS:
                log.warning(f"Invalid signal '{signal}' in column '{col}', corrected to N/A")
                corrections[col] = "N/A"

        # Coerce non-signal 'N/A' or '-' strings to None to prevent Strategy TypeErrors
        for col, val in row.items():
            if col not in EXCEL_COLUMNS and val in ("N/A", "-"):
                corrections[col] = None

        # ----- Check 4: Staleness detection -----
        if price == self._last_price:
            self._consecutive_same_price += 1
            if self._consecutive_same_price >= STALENESS_THRESHOLD:
                log.warning(
                    f"Price has been {price} for {self._consecutive_same_price} "
                    f"consecutive reads — data feed may be stale"
                )
                # Still allow storage but log a warning; don't skip
        else:
            self._consecutive_same_price = 0

        # ----- Check 5: Full duplicate detection -----
        current_signals = {
            col: row.get(col) for col in EXCEL_COLUMNS if col not in ("Date-Time",)
        }
        if (
            price == self._last_price
            and self._last_signals is not None
            and current_signals == self._last_signals
        ):
            return False, "Exact duplicate of previous row (price + all signals identical)", corrections

        # Update tracking state
        self._last_price = price
        self._last_signals = current_signals

        return True, "OK", corrections

    def reset(self) -> None:
        """Reset validator state (e.g., on new day / file rotation)."""
        self._last_price = None
        self._last_signals = None
        self._consecutive_same_price = 0
