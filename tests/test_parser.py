"""Tests for core.parser — price parsing, signal normalisation, snapshot assembly."""

from __future__ import annotations

import pytest
from datetime import timezone

from core.parser import parse_price, normalise_signal, parse_snapshot


# ── parse_price ───────────────────────────────────────────────────────

class TestParsePrice:
    def test_normal_with_comma(self):
        assert parse_price("4,127.33") == 4127.33

    def test_no_comma(self):
        assert parse_price("4127.33") == 4127.33

    def test_with_dollar_sign(self):
        assert parse_price("$4,127.33") == 4127.33

    def test_with_whitespace(self):
        assert parse_price("  4127.33  ") == 4127.33

    def test_none_returns_none(self):
        assert parse_price(None) is None

    def test_empty_string_returns_none(self):
        assert parse_price("") is None

    def test_garbage_returns_none(self):
        assert parse_price("abc") is None

    def test_integer_price(self):
        assert parse_price("4000") == 4000.0


# ── normalise_signal ──────────────────────────────────────────────────

class TestNormaliseSignal:
    def test_exact_match(self):
        assert normalise_signal("Strong Buy") == "Strong Buy"

    def test_case_insensitive(self):
        assert normalise_signal("strong sell") == "Strong Sell"

    def test_alias_overbought(self):
        assert normalise_signal("Overbought") == "Sell"

    def test_alias_oversold(self):
        assert normalise_signal("Oversold") == "Buy"

    def test_alias_unlock(self):
        assert normalise_signal("Unlock") == "N/A"

    def test_none_returns_na(self):
        assert normalise_signal(None) == "N/A"

    def test_empty_string_returns_na(self):
        assert normalise_signal("") == "N/A"

    def test_unknown_returns_na(self):
        assert normalise_signal("FooBar") == "N/A"

    def test_substring_match(self):
        assert normalise_signal("some Strong Buy text") == "Strong Buy"

    def test_all_valid_signals(self):
        for signal in ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell"):
            assert normalise_signal(signal) == signal


# ── parse_snapshot ────────────────────────────────────────────────────

class TestParseSnapshot:
    def test_full_row(self, valid_raw_snapshot):
        row = parse_snapshot(valid_raw_snapshot)
        assert row["Price"] == 4127.33
        assert row["Daily"] == "Strong Buy"
        assert row["Date-Time"].tzinfo == timezone.utc

    def test_missing_price(self):
        raw = {"price": None, "Daily": "Buy", "Weekly": "Buy"}
        row = parse_snapshot(raw)
        assert row["Price"] is None

    def test_missing_signals_default_to_na(self):
        raw = {"price": "4000"}
        row = parse_snapshot(raw)
        assert row["Daily"] == "N/A"
        assert row["Weekly"] == "N/A"
        assert row["Monthly"] == "N/A"

    def test_timestamp_is_utc(self, valid_raw_snapshot):
        row = parse_snapshot(valid_raw_snapshot)
        assert row["Date-Time"].tzinfo is not None
