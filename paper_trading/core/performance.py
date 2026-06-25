"""
performance.py -- Performance analytics and reporting for the paper trading platform.

Computes trading metrics from closed trades and produces formatted
console reports and equity-curve CSV exports.

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from paper_trading.config.settings import OUTPUT_DIR, INITIAL_CAPITAL
from paper_trading.core.order_manager import ClosedTrade
from paper_trading.utils.logger import get_logger

log = get_logger("perf")


@dataclass
class PerformanceReport:
    """Container for all computed performance metrics."""

    total_trades:       int = 0
    winning_trades:     int = 0
    losing_trades:      int = 0
    win_rate:           float = 0.0

    gross_profit:       float = 0.0
    gross_loss:         float = 0.0
    net_pnl:            float = 0.0
    profit_factor:      float = 0.0

    avg_win:            float = 0.0
    avg_loss:           float = 0.0
    expectancy:         float = 0.0

    max_drawdown:       float = 0.0
    max_drawdown_pct:   float = 0.0
    peak_equity:        float = 0.0
    final_equity:       float = 0.0

    avg_rr_achieved:    float = 0.0
    avg_risk_per_trade: float = 0.0

    max_consecutive_wins:  int = 0
    max_consecutive_losses: int = 0

    sharpe_ratio:       float = 0.0

    total_commission:   float = 0.0
    avg_holding_seconds: float = 0.0

    equity_curve:       List[Tuple[str, float]] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.equity_curve is None:
            self.equity_curve = []


class PerformanceTracker:
    """
    Computes performance metrics from a list of closed trades.

    Usage:
        tracker = PerformanceTracker(initial_capital=10000)
        report = tracker.compute(broker.closed_trades)
        tracker.print_report(report)
        tracker.export_equity_curve(report)
    """

    def __init__(self, initial_capital: float = INITIAL_CAPITAL) -> None:
        self._initial_capital = initial_capital

    def compute(self, trades: List[ClosedTrade]) -> PerformanceReport:
        """Compute all metrics from the trade list."""
        report = PerformanceReport()

        if not trades:
            report.final_equity = self._initial_capital
            return report

        report.total_trades = len(trades)

        # Win / loss classification
        winners = [t for t in trades if t.net_pnl > 0]
        losers = [t for t in trades if t.net_pnl <= 0]
        report.winning_trades = len(winners)
        report.losing_trades = len(losers)
        report.win_rate = report.winning_trades / report.total_trades

        # Profit / loss totals
        report.gross_profit = sum(t.net_pnl for t in winners)
        report.gross_loss = abs(sum(t.net_pnl for t in losers))
        report.net_pnl = sum(t.net_pnl for t in trades)
        report.profit_factor = (
            report.gross_profit / report.gross_loss
            if report.gross_loss > 0
            else float("inf")
        )

        # Averages
        report.avg_win = (
            report.gross_profit / len(winners) if winners else 0.0
        )
        report.avg_loss = (
            report.gross_loss / len(losers) if losers else 0.0
        )

        # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        loss_rate = 1.0 - report.win_rate
        report.expectancy = (
            (report.win_rate * report.avg_win) - (loss_rate * report.avg_loss)
        )

        # R:R and risk
        report.avg_rr_achieved = (
            sum(t.rr_achieved for t in trades) / len(trades)
        )
        report.avg_risk_per_trade = (
            sum(t.risk_amount for t in trades) / len(trades)
        )

        # Commission
        report.total_commission = sum(t.commission for t in trades)

        # Holding time
        report.avg_holding_seconds = (
            sum(t.holding_time_seconds for t in trades) / len(trades)
        )

        # Equity curve + drawdown
        equity = self._initial_capital
        peak = equity
        max_dd = 0.0
        max_dd_pct = 0.0
        curve = [(trades[0].open_time.isoformat(), equity)]

        for t in trades:
            equity += t.net_pnl
            curve.append((t.close_time.isoformat(), round(equity, 2)))

            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        report.equity_curve = curve
        report.max_drawdown = round(max_dd, 2)
        report.max_drawdown_pct = round(max_dd_pct, 2)
        report.peak_equity = round(peak, 2)
        report.final_equity = round(equity, 2)

        # Consecutive wins / losses
        report.max_consecutive_wins = self._max_streak(trades, win=True)
        report.max_consecutive_losses = self._max_streak(trades, win=False)

        # Sharpe ratio (simplified: using per-trade returns)
        if len(trades) >= 2:
            returns = [t.net_pnl for t in trades]
            import statistics
            mean_r = statistics.mean(returns)
            std_r = statistics.stdev(returns)
            # Annualise assuming ~252 trading days, ~10 trades/day
            report.sharpe_ratio = (
                (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0
            )

        return report

    def print_report(self, report: PerformanceReport) -> None:
        """Print a formatted performance summary to the console."""
        print()
        print("=" * 70)
        print("  PAPER TRADING PERFORMANCE REPORT")
        print("  (All results are simulated)")
        print("=" * 70)

        if report.total_trades == 0:
            print("  No trades were executed during this session.")
            print("=" * 70)
            return

        # Overview
        print(f"  {'Total Trades:':<30} {report.total_trades}")
        print(f"  {'Winners:':<30} {report.winning_trades}")
        print(f"  {'Losers:':<30} {report.losing_trades}")
        print(f"  {'Win Rate:':<30} {report.win_rate:.1%}")
        print("-" * 70)

        # P&L
        pnl_sign = "+" if report.net_pnl >= 0 else ""
        print(f"  {'Gross Profit:':<30} ${report.gross_profit:>12,.2f}")
        print(f"  {'Gross Loss:':<30} ${report.gross_loss:>12,.2f}")
        print(f"  {'Net P&L:':<30} {pnl_sign}${report.net_pnl:>11,.2f}")
        print(f"  {'Total Commission:':<30} ${report.total_commission:>12,.2f}")
        print(f"  {'Profit Factor:':<30} {report.profit_factor:>12.2f}")
        print("-" * 70)

        # Risk metrics
        print(f"  {'Avg Win:':<30} ${report.avg_win:>12,.2f}")
        print(f"  {'Avg Loss:':<30} ${report.avg_loss:>12,.2f}")
        print(f"  {'Expectancy:':<30} ${report.expectancy:>12,.2f}")
        print(f"  {'Avg R:R Achieved:':<30} {report.avg_rr_achieved:>12.2f}")
        print(f"  {'Avg Risk/Trade:':<30} ${report.avg_risk_per_trade:>12,.2f}")
        print("-" * 70)

        # Drawdown
        print(f"  {'Max Drawdown:':<30} ${report.max_drawdown:>12,.2f}")
        print(f"  {'Max Drawdown %:':<30} {report.max_drawdown_pct:>11.2f}%")
        print(f"  {'Peak Equity:':<30} ${report.peak_equity:>12,.2f}")
        print(f"  {'Final Equity:':<30} ${report.final_equity:>12,.2f}")
        print("-" * 70)

        # Streaks
        print(f"  {'Max Consecutive Wins:':<30} {report.max_consecutive_wins:>12d}")
        print(f"  {'Max Consecutive Losses:':<30} {report.max_consecutive_losses:>12d}")
        print(f"  {'Sharpe Ratio:':<30} {report.sharpe_ratio:>12.2f}")
        print(f"  {'Avg Holding Time:':<30} {report.avg_holding_seconds:>10.0f}s")
        print("=" * 70)

        # Return on capital
        roi = ((report.final_equity - self._initial_capital) / self._initial_capital) * 100
        roi_sign = "+" if roi >= 0 else ""
        print(f"  {'Return on Capital:':<30} {roi_sign}{roi:.2f}%")
        print(f"  {'Initial Capital:':<30} ${self._initial_capital:>12,.2f}")
        print(f"  {'Final Capital:':<30} ${report.final_equity:>12,.2f}")
        print("=" * 70)
        print()

    def export_equity_curve(
        self,
        report: PerformanceReport,
        filename: Optional[str] = None,
    ) -> Path:
        """Export the equity curve to a CSV file."""
        if filename is None:
            filename = f"equity_curve_{datetime.now().strftime('%Y-%m-%d')}.csv"

        path = OUTPUT_DIR / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "equity"])
            for ts, eq in report.equity_curve:
                writer.writerow([ts, eq])

        log.info(f"Equity curve exported: {path.name}")
        return path

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    def _max_streak(trades: List[ClosedTrade], win: bool) -> int:
        """Find the longest consecutive win or loss streak."""
        max_streak = 0
        current = 0
        for t in trades:
            if (win and t.is_winner) or (not win and not t.is_winner):
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak
