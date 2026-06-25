# Backtesting Extension Guide

This document outlines how to extend the XAU/USD strategy engine for historical backtesting.

---

## 1. Data Requirements

The daily Excel files produced by the pipeline already contain all the fields needed for a basic replay-style backtest:

| Column | Usage in Backtest |
|--------|-------------------|
| `Date-Time` | Event timestamp for time-series ordering |
| `Price` | Entry/exit price for simulated trades |
| `Daily`, `Weekly` | Bias determination (same rules as live) |
| `Hourly`, `5 Hours` | Entry confirmation (same rules as live) |
| `Signal` | Live strategy output — compare against backtest output |

### Collecting History

The pipeline generates ~17,280 rows per day at 5-second intervals. For meaningful backtests, aim for **at least 20–30 trading days** of data (~350K–520K rows).

To accelerate data collection, you can also source historical 1-minute or 5-minute OHLC data from:
- **OANDA API** (free with demo account)
- **TradingView** (export CSV)
- **MetaTrader 5** (Python API: `MetaTrader5` package)
- **Yahoo Finance** (`yfinance` package — limited for XAU/USD)

---

## 2. Backtest Architecture

```
Historical Data (Excel/CSV)
        │
        ▼
  ┌─────────────┐
  │  DataLoader  │  ← Reads rows chronologically
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Simulator   │  ← Feeds rows to TradingStrategy one by one
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  TradeLog    │  ← Records entries, exits, P&L per trade
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Analyzer    │  ← Computes metrics (win rate, Sharpe, drawdown)
  └─────────────┘
```

---

## 3. Scaffolding Code

```python
"""
backtester.py — Skeleton for replaying historical data through the strategy.

Place this file in the project root and run:
    python backtester.py data/xau_usd_2026-06-23.xlsx
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from core.strategy import TradingStrategy, StrategySignal
from config.settings import ACCOUNT_BALANCE


@dataclass
class Trade:
    """Record of a single simulated trade."""
    direction: str              # "LONG" or "SHORT"
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: str = ""       # "TP", "SL", "SIGNAL_FLIP", "END"


@dataclass
class BacktestResult:
    """Summary of a backtest run."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_balance: float = ACCOUNT_BALANCE
    trades: List[Trade] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.total_trades if self.total_trades else 0.0

    @property
    def profit_factor(self) -> float:
        gains = sum(t.pnl for t in self.trades if t.pnl and t.pnl > 0)
        losses = abs(sum(t.pnl for t in self.trades if t.pnl and t.pnl < 0))
        return gains / losses if losses else float('inf')

    def summary(self) -> str:
        return (
            f"Trades: {self.total_trades} | "
            f"Win Rate: {self.win_rate:.1%} | "
            f"P&L: ${self.total_pnl:,.2f} | "
            f"Max Drawdown: ${self.max_drawdown:,.2f} | "
            f"Profit Factor: {self.profit_factor:.2f}"
        )


class Backtester:
    """Replay historical data through the strategy engine."""

    def __init__(self) -> None:
        self.strategy = TradingStrategy()
        self.result = BacktestResult()
        self._open_trade: Optional[Trade] = None
        self._balance = ACCOUNT_BALANCE

    def run(self, data_path: str) -> BacktestResult:
        """
        Run backtest on an Excel file.

        The file should have the same schema as the pipeline output.
        """
        df = pd.read_excel(data_path)
        print(f"Loaded {len(df)} rows from {data_path}")

        for _, row_series in df.iterrows():
            row = row_series.to_dict()
            self._process_row(row)

        # Close any open trade at the end
        if self._open_trade:
            self._close_trade(
                row["Date-Time"], row["Price"], "END"
            )

        return self.result

    def _process_row(self, row: dict) -> None:
        """Process a single historical row."""
        price = row.get("Price")
        if price is None:
            return

        # Check stop loss / take profit on open trade
        if self._open_trade:
            self._check_exit(row)

        # Get strategy signal
        signal = self.strategy.evaluate(row)
        if signal is None:
            return

        # If signal direction flips, close existing trade
        if self._open_trade and signal.direction != self._open_trade.direction:
            self._close_trade(
                row["Date-Time"], price, "SIGNAL_FLIP"
            )

        # Open new trade if signal is LONG or SHORT and no trade open
        if not self._open_trade and signal.direction in ("LONG", "SHORT"):
            if signal.entry_price and signal.stop_loss and signal.take_profit:
                self._open_trade = Trade(
                    direction=signal.direction,
                    entry_time=row["Date-Time"],
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

    def _check_exit(self, row: dict) -> None:
        """Check if the current price hit SL or TP."""
        price = row["Price"]
        trade = self._open_trade

        if trade.direction == "LONG":
            if price <= trade.stop_loss:
                self._close_trade(row["Date-Time"], trade.stop_loss, "SL")
            elif price >= trade.take_profit:
                self._close_trade(row["Date-Time"], trade.take_profit, "TP")
        else:  # SHORT
            if price >= trade.stop_loss:
                self._close_trade(row["Date-Time"], trade.stop_loss, "SL")
            elif price <= trade.take_profit:
                self._close_trade(row["Date-Time"], trade.take_profit, "TP")

    def _close_trade(self, time: datetime, price: float, reason: str) -> None:
        """Close the open trade and record P&L."""
        trade = self._open_trade
        trade.exit_time = time
        trade.exit_price = price
        trade.exit_reason = reason

        if trade.direction == "LONG":
            trade.pnl = (price - trade.entry_price) * 100  # × lot size
        else:
            trade.pnl = (trade.entry_price - price) * 100

        self._balance += trade.pnl
        self.result.total_trades += 1
        self.result.total_pnl += trade.pnl
        self.result.trades.append(trade)

        if trade.pnl > 0:
            self.result.winning_trades += 1
        else:
            self.result.losing_trades += 1

        # Track drawdown
        if self._balance > self.result.peak_balance:
            self.result.peak_balance = self._balance
        drawdown = self.result.peak_balance - self._balance
        if drawdown > self.result.max_drawdown:
            self.result.max_drawdown = drawdown

        self._open_trade = None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backtester.py <path_to_excel_file>")
        sys.exit(1)

    bt = Backtester()
    result = bt.run(sys.argv[1])
    print(f"\n{result.summary()}")

    # Print individual trades
    for i, t in enumerate(result.trades, 1):
        print(
            f"  #{i}: {t.direction} @ {t.entry_price:,.2f} -> "
            f"{t.exit_price:,.2f} ({t.exit_reason}) "
            f"P&L: ${t.pnl:,.2f}"
        )
```

---

## 4. Key Metrics to Track

| Metric | Formula | Good Target |
|--------|---------|-------------|
| **Win Rate** | wins / total_trades | > 40% (with 1:2 RR) |
| **Profit Factor** | gross_profit / gross_loss | > 1.5 |
| **Max Drawdown** | peak_balance - trough_balance | < 20% of account |
| **Sharpe Ratio** | mean(returns) / std(returns) × √252 | > 1.0 |
| **Expectancy** | (win_rate × avg_win) - (loss_rate × avg_loss) | > 0 |
| **Max Consecutive Losses** | Longest losing streak | < 8 |
| **Recovery Factor** | total_pnl / max_drawdown | > 2.0 |

---

## 5. Recommended Libraries

| Library | Best For | Notes |
|---------|----------|-------|
| **vectorbt** | Fast vectorised backtesting | Best for signal-based strategies like ours |
| **backtrader** | Event-driven backtesting | More complex but very flexible |
| **zipline-reloaded** | Full portfolio backtesting | Overkill for single-instrument |
| **QuantStats** | Performance reporting | Beautiful tear sheets, Sharpe, drawdown plots |
| **matplotlib / plotly** | Custom visualisation | Equity curves, trade markers on price charts |

### Quick Start with vectorbt

```python
import vectorbt as vbt
import pandas as pd

# Load data
df = pd.read_excel("data/xau_usd_2026-06-23.xlsx", index_col="Date-Time")

# Create entry/exit signals from the strategy column
entries = df["Signal"] == "LONG"
exits = df["Signal"].isin(["SHORT", "FLAT"])

# Run backtest
pf = vbt.Portfolio.from_signals(
    df["Price"],
    entries=entries,
    exits=exits,
    init_cash=10_000,
    fees=0.001,     # 0.1% spread/commission
    freq="5s",
)

print(pf.stats())
pf.plot().show()
```

---

## 6. Important Caveats

1. **Spread / Slippage**: The scraped price is a mid-price. Real execution has spread (~$0.30–$0.50 for XAU/USD). Always add spread to backtest results.

2. **Look-Ahead Bias**: The strategy evaluates signals at the moment they are scraped. Ensure the backtest uses the same ordering — never peek at future rows.

3. **ATR Warm-Up**: The ATR approximator needs ~14 windows (~70 min at 5s ticks) to warm up. The first hour of data will show FLAT signals regardless of market conditions.

4. **Market Hours**: XAU/USD trades ~23 hours/day (Sunday 5 PM – Friday 5 PM ET). Weekend data gaps are normal and should not trigger false signals.

5. **Survivorship of Signals**: Investing.com's signals are recomputed continuously. A "Strong Buy" at 10:00 AM may become "Neutral" by 10:01 AM. This is inherent to the data source.

6. **Overfitting**: With only 5-second sentiment data (not OHLC), be cautious about optimising thresholds. Use walk-forward validation and out-of-sample testing.
