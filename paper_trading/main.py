"""
main.py -- Entry point for the XAU/USD paper trading platform.

Two operating modes:

    1. LIVE (dry-run): Connects to the real-time pipeline and paper-trades
       incoming signals.  Uses the same scraper, parser, validator, and
       strategy as the main pipeline.

    2. REPLAY: Reads rows from a historical Excel file, feeds each row
       through the strategy engine, and simulates execution.

Usage:
    # Live dry-run mode
    python -m paper_trading.main --mode live

    # Historical replay mode
    python -m paper_trading.main --mode replay --file data/xau_usd_2026-06-23.xlsx

    # Replay with custom capital
    python -m paper_trading.main --mode replay --file data/xau_usd_2026-06-23.xlsx --capital 50000

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
from datetime import datetime
from typing import Optional

from paper_trading.config.settings import (
    INITIAL_CAPITAL,
    OUTPUT_DIR,
    DATA_DIR,
    print_banner,
)
from paper_trading.core.order_manager import ClosedTrade, make_event
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from paper_trading.core.signal_router import SignalRouter
from paper_trading.core.journal import TradeJournal
from paper_trading.core.performance import PerformanceTracker
from paper_trading.utils.logger import get_logger

import requests

log = get_logger("main")

# ── Global shutdown flag ──────────────────────────────────────────────
_shutdown = False

def _push_event_to_api(event_type: str, payload: dict) -> None:
    try:
        requests.post("http://localhost:8000/api/v1/internal/event", json={
            "type": event_type,
            "payload": payload
        }, timeout=0.5)
    except Exception:
        pass

def _handle_broker_event(e, journal) -> None:
    journal.record_event(e)
    _push_event_to_api(e.get("type", "UNKNOWN"), e)



def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n[!] Shutdown requested -- finishing current cycle...")


# ── Replay mode ──────────────────────────────────────────────────────

def run_replay(file_path: str, capital: float) -> None:
    """
    Replay historical data through the paper trading engine.

    Reads rows from an Excel file, feeds each through the strategy,
    and simulates execution with the paper broker.
    """
    import pandas as pd
    from core.strategy import TradingStrategy

    log.info(f"REPLAY MODE: Loading {file_path}")

    # Load data
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        log.error(f"Failed to load file: {e}")
        print(f"  [ERROR] Cannot read file: {file_path}")
        print(f"  {e}")
        return

    if df.empty:
        log.error("File is empty -- nothing to replay")
        return

    total_rows = len(df)
    print(f"  Loaded {total_rows:,} rows from {Path(file_path).name}")
    print(f"  Date range: {df.iloc[0].get('Date-Time', '?')} -> {df.iloc[-1].get('Date-Time', '?')}")
    print()

    # Initialise components
    journal = TradeJournal()
    broker = PaperBroker(
        initial_capital=capital,
        on_event=lambda e: _handle_broker_event(e, journal),
    )
    risk_mgr = RiskManager(initial_capital=capital)
    router = SignalRouter(broker, risk_mgr)
    strategy = TradingStrategy()
    perf = PerformanceTracker(initial_capital=capital)

    print(f"  Processing {total_rows:,} rows...\n")

    # Process each row
    for idx, row_series in df.iterrows():
        if _shutdown:
            break

        row = row_series.to_dict()
        price = row.get("Price")
        if price is None or (isinstance(price, float) and price != price):  # NaN check
            continue

        # Convert timestamp
        ts = row.get("Date-Time")
        if ts is not None and not isinstance(ts, datetime):
            try:
                ts = pd.Timestamp(ts).to_pydatetime()
                row["Date-Time"] = ts
            except Exception:
                row["Date-Time"] = datetime.now()
                ts = row["Date-Time"]

        # Feed to strategy
        signal = strategy.evaluate(row)

        # Tick broker (check SL/TP on open positions)
        closed_trades = broker.tick(price, timestamp=ts)
        for t in closed_trades:
            risk_mgr.record_trade_result(t.net_pnl, timestamp=ts)
            journal.record_trade(t)
            
        # Push periodic position update
        if broker.open_positions:
            _push_event_to_api("POSITION_UPDATE", {
                "positions": [{"position_id": p.position_id, "unrealised_pnl": p.unrealised_pnl} for p in broker.open_positions],
                "total_unrealised_pnl": sum(p.unrealised_pnl for p in broker.open_positions)
            })

        # Route signal
        if signal is not None and signal.direction != "FLAT":
            router.process_signal(signal, current_price=price, timestamp=ts)

        # Progress indicator
        if (idx + 1) % 1000 == 0 or idx == total_rows - 1:
            pct = ((idx + 1) / total_rows) * 100
            pos_count = broker.open_position_count
            trade_count = len(broker.closed_trades)
            print(
                f"\r  [{pct:5.1f}%] Row {idx+1:,}/{total_rows:,} | "
                f"Price: ${price:,.2f} | "
                f"Equity: ${broker.equity:,.2f} | "
                f"Open: {pos_count} | "
                f"Closed: {trade_count} | "
                f"Signals: {router.signals_received}",
                end="", flush=True,
            )

    # Close remaining positions
    if broker.open_position_count > 0:
        last_price = df.iloc[-1].get("Price", 0)
        last_ts = df.iloc[-1].get("Date-Time", datetime.now())
        if not isinstance(last_ts, datetime):
            try:
                import pandas as pd
                last_ts = pd.Timestamp(last_ts).to_pydatetime()
            except Exception:
                last_ts = datetime.now()
        closed = broker.close_all_positions(
            price=last_price, timestamp=last_ts
        )
        for t in closed:
            risk_mgr.record_trade_result(t.net_pnl, timestamp=last_ts)
            journal.record_trade(t)

    print("\n")

    # Finalise
    _finalise_session(broker, journal, perf, router, risk_mgr)


# ── Live dry-run mode ─────────────────────────────────────────────────

def run_live(capital: float) -> None:
    """
    Live dry-run mode: connects to the real-time scraper pipeline
    and paper-trades incoming signals.
    """
    global _shutdown
    
    from core.scraper import GoldScraper
    from core.parser import parse_snapshot
    from core.validator import DataValidator
    from core.strategy import TradingStrategy
    from config.settings import (
        REFRESH_INTERVAL_SECONDS,
        MAX_RETRIES,
        RETRY_BASE_DELAY_SECONDS,
    )

    log.info("LIVE DRY-RUN MODE: Connecting to real-time pipeline")

    # Initialise components
    journal = TradeJournal()
    risk_mgr = RiskManager(initial_capital=capital)
    broker = PaperBroker(
        initial_capital=capital,
        on_event=lambda e: _handle_broker_event(e, journal),
    )
    router = SignalRouter(broker, risk_mgr)
    strategy = TradingStrategy()
    validator = DataValidator()
    perf = PerformanceTracker(initial_capital=capital)

    # Launch browser
    scraper = GoldScraper()
    cycle = 0

    try:
        log.info("Starting browser for live paper trading...")
        scraper.start()
        log.info("Browser ready. Paper trading active.")
        print("  Live paper trading active. Press Ctrl+C to stop.\n")

        while not _shutdown:
            cycle += 1
            cycle_start = time.time()

            try:
                # Scrape
                raw = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        raw = scraper.read_snapshot()
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES:
                            time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))

                if raw is None:
                    time.sleep(REFRESH_INTERVAL_SECONDS)
                    continue

                # Parse + validate
                row = parse_snapshot(raw)
                is_valid, reason, corrections = validator.validate(row)
                if corrections:
                    row.update(corrections)

                price = row.get("Price")
                if price is None:
                    time.sleep(REFRESH_INTERVAL_SECONDS)
                    continue

                ts = row.get("Date-Time", datetime.now())

                # Tick broker
                closed_trades = broker.tick(price, timestamp=ts)
                for t in closed_trades:
                    risk_mgr.record_trade_result(t.net_pnl)
                    journal.record_trade(t)

                # Push periodic position update
                if broker.open_positions:
                    _push_event_to_api("POSITION_UPDATE", {
                        "positions": [{"position_id": p.position_id, "unrealised_pnl": p.unrealised_pnl} for p in broker.open_positions],
                        "total_unrealised_pnl": sum(p.unrealised_pnl for p in broker.open_positions)
                    })

                # Strategy
                signal = strategy.evaluate(row)
                if signal is not None and signal.direction != "FLAT":
                    router.process_signal(signal, current_price=price, timestamp=ts)

                # Dashboard
                dir_str = signal.direction if signal else "---"
                dir_icon = {"LONG": "^ LONG", "SHORT": "v SHORT", "FLAT": "- FLAT"}.get(
                    dir_str, "- ---"
                )
                print(
                    f"\r  #{cycle:<5} | {ts:%H:%M:%S} | ${price:>10,.2f} | "
                    f"{dir_icon:<9} | "
                    f"Eq: ${broker.equity:>10,.2f} | "
                    f"Open: {broker.open_position_count} | "
                    f"Trades: {len(broker.closed_trades)} | "
                    f"P&L: ${sum(t.net_pnl for t in broker.closed_trades):>+10,.2f}",
                    end="", flush=True,
                )

            except KeyboardInterrupt:
                _shutdown = True
                break
            except Exception as e:
                log.error(f"Error in cycle #{cycle}: {e}", exc_info=True)

            elapsed = time.time() - cycle_start
            sleep_time = max(0, REFRESH_INTERVAL_SECONDS - elapsed)
            if sleep_time > 0 and not _shutdown:
                time.sleep(sleep_time)

    except Exception as e:
        log.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        # Close open positions at last price
        if broker.open_position_count > 0:
            log.info("Closing open positions at session end...")
            closed = broker.close_all_positions(price=price if price else 0)
            for t in closed:
                risk_mgr.record_trade_result(t.net_pnl)
                journal.record_trade(t)

        scraper.stop()
        print("\n")
        _finalise_session(broker, journal, perf, router, risk_mgr)


# ── Shared helpers ────────────────────────────────────────────────────

def _on_trade_closed(
    trade: ClosedTrade,
    journal: TradeJournal,
    risk_mgr: RiskManager,
) -> None:
    """Callback invoked when the broker closes a trade via SL/TP."""
    risk_mgr.record_trade_result(trade.net_pnl)
    journal.record_trade(trade)


def _finalise_session(
    broker: PaperBroker,
    journal: TradeJournal,
    perf: PerformanceTracker,
    router: SignalRouter,
    risk_mgr: RiskManager,
) -> None:
    """Print final report, save journal, and export equity curve."""

    # Write Excel journal
    journal.flush_excel()

    # Compute and print performance
    report = perf.compute(broker.closed_trades)
    perf.print_report(report)

    # Export equity curve
    if report.equity_curve:
        perf.export_equity_curve(report)

    # Log rejections
    if risk_mgr.rejections:
        print(f"  Rejected orders: {len(risk_mgr.rejections)}")
        for r in risk_mgr.rejections[:5]:  # Show first 5
            print(f"    - #{r.order_id} {r.side.value}: {r.rejection_reason}")
        if len(risk_mgr.rejections) > 5:
            print(f"    ... and {len(risk_mgr.rejections) - 5} more")

    # Summary
    print()
    print(f"  Signal router: {router.signals_received} received, "
          f"{router.signals_acted} acted, "
          f"{router.signals_skipped} skipped")
    print(f"  Output directory: {OUTPUT_DIR}")
    if journal.trades:
        print(f"  CSV journal:   {journal.csv_path.name}")
        print(f"  Excel journal: {journal.xlsx_path.name}")
        print(f"  Event log:     {journal.jsonl_path.name}")
    print()
    print("  Paper trading only. No live execution. All results are simulated.")
    print()


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="XAU/USD Paper Trading Platform (Simulation Only)",
        epilog="Paper trading only. No live execution. All results are simulated.",
    )
    parser.add_argument(
        "--mode",
        choices=["live", "replay"],
        default="replay",
        help="Operating mode: 'live' for real-time dry-run, 'replay' for historical",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to historical Excel file (required for replay mode)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help=f"Starting capital (default: ${INITIAL_CAPITAL:,.0f})",
    )

    args = parser.parse_args()
    capital = args.capital or INITIAL_CAPITAL

    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Print banner
    print_banner()

    if args.mode == "replay":
        if args.file is None:
            # Try to find the most recent data file
            xlsx_files = sorted(DATA_DIR.glob("xau_usd_*.xlsx"))
            if xlsx_files:
                file_path = str(xlsx_files[-1])
                print(f"  No --file specified. Using most recent: {Path(file_path).name}")
            else:
                print("  [ERROR] No --file specified and no data files found in data/")
                print("  Usage: python -m paper_trading.main --mode replay --file <path>")
                sys.exit(1)
        else:
            file_path = args.file

        run_replay(file_path, capital)

    elif args.mode == "live":
        run_live(capital)


if __name__ == "__main__":
    main()
