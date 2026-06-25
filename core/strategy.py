"""
strategy.py — Rule-based XAU/USD trading strategy engine.

Consumes scraped technical-analysis signals and produces advisory
long/short/flat decisions with full risk-management parameters.

Rules:
    1. Daily + Weekly define directional bias.
    2. Hourly + 5-Hours (H4 proxy) confirm entries.
    3. ATR-based stop loss (approximated from price history).
    4. Minimum 1:2 reward-to-risk ratio.
    5. 0.5 % to 1 % risk per trade.
    6. Only aligned setups are traded.

Usage:
    strategy = TradingStrategy()
    signal = strategy.evaluate(parsed_row)
    print(signal)
"""

from __future__ import annotations

import json
import statistics
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import (
    ACCOUNT_BALANCE,
    RISK_PER_TRADE_PCT,
    MIN_REWARD_RISK_RATIO,
    ATR_PERIOD,
    ATR_STOP_MULTIPLIER,
    LOT_SIZE,
    STRATEGY_EVAL_INTERVAL,
    DATA_DIR,
)
from utils.logger import get_logger

log = get_logger("strategy")

# ── Signal scoring ────────────────────────────────────────────────────
# Maps the sentiment strings returned by Investing.com to numeric scores
# used for bias/alignment evaluation.
_SIGNAL_SCORE: Dict[str, int] = {
    "Strong Buy":   2,
    "Buy":          1,
    "Neutral":      0,
    "Sell":        -1,
    "Strong Sell": -2,
    "N/A":          0,
}

# Minimum absolute score sum (higher-timeframe) to declare a bias
_BIAS_THRESHOLD = 2

# Minimum absolute score sum (confirmation timeframes) to confirm entry
_CONFIRM_THRESHOLD = 1


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class StrategySignal:
    """Immutable output of a single strategy evaluation cycle."""

    timestamp:        datetime
    direction:        str           # "LONG", "SHORT", or "FLAT"
    bias:             str           # e.g. "Bullish (Daily=Buy, Weekly=Strong Buy)"
    entry_confirmed:  bool
    confidence:       str           # "HIGH", "MEDIUM", "LOW"
    entry_price:      Optional[float] = None
    stop_loss:        Optional[float] = None
    take_profit:      Optional[float] = None
    position_size_lots: Optional[float] = None
    risk_amount:      Optional[float] = None
    reason:           str = ""

    # -- Convenience ------------------------------------------------

    def to_row_dict(self) -> Dict[str, Any]:
        """Return a dict whose keys match STRATEGY_COLUMNS in settings."""
        return {
            "Signal":           self.direction,
            "Bias":             self.bias,
            "Confidence":       self.confidence,
            "Entry":            self.entry_price,
            "Stop Loss":        self.stop_loss,
            "Take Profit":      self.take_profit,
            "Risk ($)":         round(self.risk_amount, 2) if self.risk_amount else None,
            "Position (lots)":  round(self.position_size_lots, 4) if self.position_size_lots else None,
            "Reason":           self.reason,
        }

    def __str__(self) -> str:
        if self.direction == "FLAT":
            return f"[{self.timestamp:%H:%M:%S}] FLAT -- {self.reason}"
        return (
            f"[{self.timestamp:%H:%M:%S}] {self.direction} "
            f"@ {self.entry_price:,.2f}  "
            f"SL={self.stop_loss:,.2f}  TP={self.take_profit:,.2f}  "
            f"Risk=${self.risk_amount:,.2f}  Lots={self.position_size_lots:.4f}  "
            f"({self.confidence}) -- {self.reason}"
        )


# ── ATR Approximator ─────────────────────────────────────────────────

class ATRApproximator:
    """
    Approximate ATR from a rolling window of scraped prices.

    Because Investing.com does not expose raw OHLC or ATR values, this
    class tracks observed prices over time and computes a volatility
    proxy: the average of per-window (high − low) ranges.

    A single scraped price every N seconds is NOT the same as a proper
    candlestick feed.  This is a *best-effort* approximation.  For
    production trading, replace this with an API-sourced ATR.
    """

    def __init__(self, period: int = ATR_PERIOD, window_size: int = 60) -> None:
        """
        Args:
            period:      Number of range windows to average.
            window_size: Number of ticks per range window (e.g. 60 ticks
                         at 5 s ≈ 5 minutes per window).
        """
        self._period = period
        self._window_size = window_size
        self._current_window: List[float] = []
        self._ranges: deque[float] = deque(maxlen=period)
        self._atr: Optional[float] = None

    def update(self, price: float) -> None:
        """Feed a new price tick."""
        self._current_window.append(price)

        if len(self._current_window) >= self._window_size:
            hi = max(self._current_window)
            lo = min(self._current_window)
            self._ranges.append(hi - lo)
            self._current_window.clear()

            if len(self._ranges) >= 2:
                self._atr = statistics.mean(self._ranges)

    @property
    def atr(self) -> Optional[float]:
        """Current ATR estimate, or None if insufficient data."""
        return self._atr

    @property
    def ready(self) -> bool:
        return self._atr is not None

    @property
    def data_points(self) -> int:
        """Number of completed range windows."""
        return len(self._ranges)

    def save_state(self) -> Dict[str, Any]:
        """Serialise internal state for persistence."""
        return {
            "current_window": list(self._current_window),
            "ranges": list(self._ranges),
            "atr": self._atr,
            "period": self._period,
            "window_size": self._window_size,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Restore internal state from a previously saved dict."""
        try:
            self._current_window = list(state.get("current_window", []))
            self._ranges = deque(state.get("ranges", []), maxlen=self._period)
            self._atr = state.get("atr")
            log.info(
                f"ATR state restored: {len(self._ranges)} windows, "
                f"ATR={self._atr:.4f}" if self._atr else "ATR state restored (not ready yet)"
            )
        except Exception as e:
            log.warning(f"Failed to load ATR state: {e} — starting fresh")


# ── Strategy Engine ──────────────────────────────────────────────────

class TradingStrategy:
    """
    Rule-based XAU/USD strategy.

    Call ``evaluate(row)`` with each parsed data row.  The strategy
    only emits a decision every ``STRATEGY_EVAL_INTERVAL`` cycles
    (to avoid flooding with duplicate signals), but the ATR estimator
    is updated on every tick.
    """

    def __init__(self) -> None:
        self._atr = ATRApproximator(
            period=ATR_PERIOD,
            window_size=60,  # ~5 min window at 5 s tick
        )
        self._cycle: int = 0
        self._last_signal: Optional[StrategySignal] = None
        log.info(
            f"Strategy initialised: balance=${ACCOUNT_BALANCE:,.0f}, "
            f"risk={RISK_PER_TRADE_PCT*100:.1f}%, "
            f"min RR=1:{MIN_REWARD_RISK_RATIO:.0f}, "
            f"ATR period={ATR_PERIOD}"
        )

    # ── Public API ────────────────────────────────────────────────

    def evaluate(self, row: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        Evaluate the strategy for a parsed data row.

        Returns a StrategySignal if this is an evaluation cycle,
        or None if the cycle is skipped (inter-evaluation gap).
        The ATR estimator is *always* updated regardless.
        """
        price = row.get("Price")
        if price is not None:
            self._atr.update(price)

        self._cycle += 1
        if self._cycle % STRATEGY_EVAL_INTERVAL != 0:
            return self._last_signal  # Re-use previous signal for Excel

        signal = self._compute_signal(row)
        self._last_signal = signal

        if signal.direction != "FLAT":
            log.info(f"Strategy signal: {signal}")
        else:
            log.debug(f"Strategy signal: {signal}")

        return signal

    # ── Private logic ─────────────────────────────────────────────

    def _compute_signal(self, row: Dict[str, Any]) -> StrategySignal:
        """Core decision logic."""
        now = row.get("Date-Time", datetime.now())
        price = row.get("Price")

        if price is None:
            return self._flat(now, "Price unavailable")

        # ── Step 1: Higher-timeframe bias (Daily + Weekly) ────────
        daily_sig   = row.get("Daily", "N/A")
        weekly_sig  = row.get("Weekly", "N/A")
        monthly_sig = row.get("Monthly", "N/A")

        daily_score  = _SIGNAL_SCORE.get(daily_sig, 0)
        weekly_score = _SIGNAL_SCORE.get(weekly_sig, 0)
        bias_score   = daily_score + weekly_score

        if bias_score >= _BIAS_THRESHOLD:
            bias_dir = "LONG"
            bias_label = f"Bullish (Daily={daily_sig}, Weekly={weekly_sig})"
        elif bias_score <= -_BIAS_THRESHOLD:
            bias_dir = "SHORT"
            bias_label = f"Bearish (Daily={daily_sig}, Weekly={weekly_sig})"
        else:
            return self._flat(
                now,
                f"No clear bias: Daily={daily_sig} ({daily_score:+d}), "
                f"Weekly={weekly_sig} ({weekly_score:+d}), "
                f"sum={bias_score:+d} (need >={_BIAS_THRESHOLD} or <=-{_BIAS_THRESHOLD})"
            )

        # ── Step 2: Entry confirmation (Hourly + 5 Hours) ────────
        h1_sig  = row.get("Hourly", "N/A")
        h4_sig  = row.get("5 Hours", "N/A")   # H4 proxy

        h1_score = _SIGNAL_SCORE.get(h1_sig, 0)
        h4_score = _SIGNAL_SCORE.get(h4_sig, 0)
        confirm_score = h1_score + h4_score

        if bias_dir == "LONG" and confirm_score < _CONFIRM_THRESHOLD:
            return self._flat(
                now,
                f"Bias bullish but entry NOT confirmed: "
                f"H1={h1_sig} ({h1_score:+d}), H4={h4_sig} ({h4_score:+d}), "
                f"sum={confirm_score:+d} (need >={_CONFIRM_THRESHOLD})",
                bias=bias_label,
            )
        elif bias_dir == "SHORT" and confirm_score > -_CONFIRM_THRESHOLD:
            return self._flat(
                now,
                f"Bias bearish but entry NOT confirmed: "
                f"H1={h1_sig} ({h1_score:+d}), H4={h4_sig} ({h4_score:+d}), "
                f"sum={confirm_score:+d} (need <=-{_CONFIRM_THRESHOLD})",
                bias=bias_label,
            )

        # ── Step 3: ATR check ────────────────────────────────────
        if not self._atr.ready:
            return self._flat(
                now,
                f"ATR not ready ({self._atr.data_points}/{ATR_PERIOD} windows). "
                f"Collecting price data...",
                bias=bias_label,
            )

        atr = self._atr.atr
        if atr is None or atr < 0.01:
            return self._flat(
                now,
                f"ATR too small ({atr}) -- market may be closed or stale",
                bias=bias_label,
            )

        # ── Step 4: Compute stop / take-profit / sizing ──────────
        stop_distance = atr * ATR_STOP_MULTIPLIER

        if bias_dir == "LONG":
            stop_loss   = price - stop_distance
            take_profit = price + (stop_distance * MIN_REWARD_RISK_RATIO)
        else:
            stop_loss   = price + stop_distance
            take_profit = price - (stop_distance * MIN_REWARD_RISK_RATIO)

        # Risk amount in USD
        risk_amount = ACCOUNT_BALANCE * RISK_PER_TRADE_PCT

        # Position size: risk_amount / (stop_distance per unit)
        # For XAU/USD, 1 lot = LOT_SIZE oz, so P&L per lot = price_change × LOT_SIZE
        position_lots = risk_amount / (stop_distance * LOT_SIZE)

        # ── Step 5: Confidence scoring ───────────────────────────
        confidence = self._score_confidence(
            bias_score, confirm_score, monthly_sig, atr, price
        )

        reason = (
            f"Aligned {bias_dir}: bias={bias_score:+d} "
            f"(D={daily_sig}, W={weekly_sig}), "
            f"confirm={confirm_score:+d} (H1={h1_sig}, H4={h4_sig}), "
            f"ATR={atr:.2f}, stop_dist={stop_distance:.2f}"
        )

        return StrategySignal(
            timestamp=now,
            direction=bias_dir,
            bias=bias_label,
            entry_confirmed=True,
            confidence=confidence,
            entry_price=round(price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            position_size_lots=round(position_lots, 4),
            risk_amount=round(risk_amount, 2),
            reason=reason,
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _flat(
        self,
        ts: datetime,
        reason: str,
        bias: str = "Undetermined",
    ) -> StrategySignal:
        """Convenience factory for a FLAT (no-trade) signal."""
        return StrategySignal(
            timestamp=ts,
            direction="FLAT",
            bias=bias,
            entry_confirmed=False,
            confidence="LOW",
            reason=reason,
        )

    @staticmethod
    def _score_confidence(
        bias_score: int,
        confirm_score: int,
        monthly_sig: str,
        atr: float,
        price: float,
    ) -> str:
        """
        Heuristic confidence rating.

        HIGH:   Strong bias + strong confirmation + monthly aligned
        MEDIUM: Moderate bias or confirmation, partially aligned
        LOW:    Marginal alignment (shouldn't normally reach here)
        """
        monthly_score = _SIGNAL_SCORE.get(monthly_sig, 0)

        # Total conviction = sum of all absolute contributions
        abs_total = abs(bias_score) + abs(confirm_score)

        # Monthly agreement bonus
        if (bias_score > 0 and monthly_score > 0) or \
           (bias_score < 0 and monthly_score < 0):
            abs_total += abs(monthly_score)

        # ATR as a fraction of price: > 0.5% is decent volatility
        volatility_pct = (atr / price) * 100 if price else 0
        if volatility_pct > 0.5:
            abs_total += 1

        if abs_total >= 7:
            return "HIGH"
        elif abs_total >= 4:
            return "MEDIUM"
        else:
            return "LOW"

    # ── Properties ────────────────────────────────────────────────

    @property
    def last_signal(self) -> Optional[StrategySignal]:
        return self._last_signal

    @property
    def atr_ready(self) -> bool:
        return self._atr.ready

    @property
    def atr_value(self) -> Optional[float]:
        return self._atr.atr

    # ── ATR State Persistence ─────────────────────────────────────

    _ATR_STATE_FILE = DATA_DIR / "atr_state.json"

    def save_atr_state(self) -> None:
        """Persist ATR approximator state to disk for restart recovery."""
        try:
            state = self._atr.save_state()
            state["cycle"] = self._cycle
            self._ATR_STATE_FILE.write_text(
                json.dumps(state, indent=2), encoding="utf-8"
            )
            log.debug(f"ATR state saved to {self._ATR_STATE_FILE.name}")
        except Exception as e:
            log.warning(f"Failed to save ATR state: {e}")

    def load_atr_state(self) -> None:
        """Load ATR approximator state from disk if available."""
        if not self._ATR_STATE_FILE.exists():
            return
        try:
            state = json.loads(self._ATR_STATE_FILE.read_text(encoding="utf-8"))
            self._atr.load_state(state)
            self._cycle = state.get("cycle", 0)
            log.info(f"ATR state loaded from {self._ATR_STATE_FILE.name}")
        except Exception as e:
            log.warning(f"Failed to load ATR state: {e} — starting fresh")
