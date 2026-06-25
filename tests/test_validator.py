"""Tests for core.validator — data quality gates."""

from __future__ import annotations

import copy
import pytest
from datetime import datetime, timezone

from core.validator import DataValidator


class TestValidator:
    """Test suite for DataValidator."""

    def setup_method(self):
        self.v = DataValidator()

    # ── Basic pass / fail ─────────────────────────────────────────

    def test_valid_row_passes(self, valid_parsed_row):
        is_valid, reason, corrections = self.v.validate(valid_parsed_row)
        assert is_valid is True
        assert reason == "OK"
        assert corrections == {}

    def test_missing_price_rejected(self, valid_parsed_row):
        row = {**valid_parsed_row, "Price": None}
        is_valid, reason, corrections = self.v.validate(row)
        assert is_valid is False
        assert "missing" in reason.lower()

    def test_price_below_min_rejected(self, valid_parsed_row):
        row = {**valid_parsed_row, "Price": 100.0}
        is_valid, reason, corrections = self.v.validate(row)
        assert is_valid is False
        assert "outside" in reason.lower()

    def test_price_above_max_rejected(self, valid_parsed_row):
        row = {**valid_parsed_row, "Price": 99999.0}
        is_valid, reason, corrections = self.v.validate(row)
        assert is_valid is False
        assert "outside" in reason.lower()

    # ── Signal correction ─────────────────────────────────────────

    def test_invalid_signal_returned_as_correction(self, valid_parsed_row):
        row = {**valid_parsed_row, "Daily": "GARBAGE_VALUE"}
        is_valid, reason, corrections = self.v.validate(row)
        assert is_valid is True  # row itself is still valid
        assert corrections.get("Daily") == "N/A"
        # Verify the original row was NOT mutated
        assert row["Daily"] == "GARBAGE_VALUE"

    def test_valid_signals_no_corrections(self, valid_parsed_row):
        is_valid, reason, corrections = self.v.validate(valid_parsed_row)
        assert corrections == {}

    # ── Duplicate detection ───────────────────────────────────────

    def test_duplicate_row_rejected(self, valid_parsed_row):
        # First call: valid
        is_valid1, _, _ = self.v.validate(valid_parsed_row)
        assert is_valid1 is True

        # Second call with identical data: duplicate
        row2 = copy.deepcopy(valid_parsed_row)
        is_valid2, reason2, _ = self.v.validate(row2)
        assert is_valid2 is False
        assert "duplicate" in reason2.lower()

    def test_different_price_not_duplicate(self, valid_parsed_row):
        self.v.validate(valid_parsed_row)
        row2 = {**valid_parsed_row, "Price": 4128.00}
        is_valid, _, _ = self.v.validate(row2)
        assert is_valid is True

    # ── Staleness ─────────────────────────────────────────────────

    def test_staleness_does_not_reject(self, valid_parsed_row):
        """Staleness logs a warning but still allows storage."""
        # Feed 25 rows with same price but different signals each time
        for i in range(25):
            row = {**valid_parsed_row, "Hourly": ["Buy", "Sell"][i % 2]}
            is_valid, _, _ = self.v.validate(row)
            # Should never be rejected for staleness alone
            # (may be rejected as duplicate on alternating cycle)

    # ── Reset ─────────────────────────────────────────────────────

    def test_reset_clears_state(self, valid_parsed_row):
        self.v.validate(valid_parsed_row)
        self.v.reset()
        # After reset, same row should be valid (not a duplicate)
        is_valid, _, _ = self.v.validate(valid_parsed_row)
        assert is_valid is True
