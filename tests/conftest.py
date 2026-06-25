"""
Shared pytest fixtures for the InvPro test suite.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from typing import Dict, Any


@pytest.fixture
def valid_raw_snapshot() -> Dict[str, str]:
    """Raw scraper output with all fields populated."""
    return {
        "price": "4,127.33",
        "1 min": "Strong Sell",
        "5 min": "Buy",
        "15 min": "Neutral",
        "30 min": "Buy",
        "Hourly": "Strong Sell",
        "5 Hours": "Sell",
        "Daily": "Strong Buy",
        "Weekly": "Strong Buy",
        "Monthly": "Strong Buy",
    }


@pytest.fixture
def valid_parsed_row() -> Dict[str, Any]:
    """Parsed data row matching the Excel schema."""
    return {
        "Date-Time": datetime(2026, 6, 23, 20, 35, 48, tzinfo=timezone.utc),
        "Price": 4127.33,
        "1 min": "Strong Sell",
        "5 min": "Buy",
        "15 min": "Neutral",
        "30 min": "Buy",
        "Hourly": "Strong Sell",
        "5 Hours": "Sell",
        "Daily": "Strong Buy",
        "Weekly": "Strong Buy",
        "Monthly": "Strong Buy",
    }


@pytest.fixture
def bullish_row() -> Dict[str, Any]:
    """Row that should trigger a LONG bias + confirmed entry."""
    return {
        "Date-Time": datetime(2026, 6, 23, 14, 0, 0, tzinfo=timezone.utc),
        "Price": 4100.00,
        "1 min": "Buy",
        "5 min": "Buy",
        "15 min": "Buy",
        "30 min": "Buy",
        "Hourly": "Strong Buy",
        "5 Hours": "Buy",
        "Daily": "Strong Buy",
        "Weekly": "Strong Buy",
        "Monthly": "Strong Buy",
    }


@pytest.fixture
def bearish_row() -> Dict[str, Any]:
    """Row that should trigger a SHORT bias + confirmed entry."""
    return {
        "Date-Time": datetime(2026, 6, 23, 14, 0, 0, tzinfo=timezone.utc),
        "Price": 4100.00,
        "1 min": "Sell",
        "5 min": "Sell",
        "15 min": "Sell",
        "30 min": "Sell",
        "Hourly": "Strong Sell",
        "5 Hours": "Sell",
        "Daily": "Strong Sell",
        "Weekly": "Strong Sell",
        "Monthly": "Strong Sell",
    }


@pytest.fixture
def neutral_row() -> Dict[str, Any]:
    """Row with mixed signals — should produce FLAT."""
    return {
        "Date-Time": datetime(2026, 6, 23, 14, 0, 0, tzinfo=timezone.utc),
        "Price": 4100.00,
        "1 min": "Neutral",
        "5 min": "Neutral",
        "15 min": "Neutral",
        "30 min": "Neutral",
        "Hourly": "Buy",
        "5 Hours": "Sell",
        "Daily": "Buy",
        "Weekly": "Sell",
        "Monthly": "Neutral",
    }
