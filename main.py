"""
main.py -- Entry point for the XAU/USD Gold Trading Data Pipeline.

Runs a continuous scrape -> parse -> validate -> strategy -> store loop
every 5 seconds. Handles graceful shutdown on Ctrl+C, watchdog recovery,
and live console display with strategy signals.

Usage:
    python main.py
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import requests

# Fix Windows console encoding before any output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import (
    REFRESH_INTERVAL_SECONDS,
    MAX_RETRIES,
    RETRY_BASE_DELAY_SECONDS,
    WATCHDOG_TIMEOUT_SECONDS,
    HEALTH_FILE,
    EXCEL_COLUMNS,
    ACCOUNT_BALANCE,
    RISK_PER_TRADE_PCT,
)
from core.scraper import GoldScraper
from core.parser import parse_snapshot
from core.validator import DataValidator
from core.storage import ExcelStorage
from core.strategy import TradingStrategy
from utils.logger import get_logger

log = get_logger("main")

# ── Global state ──────────────────────────────────────────────────────
_shutdown_requested = False


def _signal_handler(sig, frame):
    """Handle Ctrl+C / SIGTERM for graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[!] Shutdown requested -- finishing current cycle...")


def _update_health(success: bool, cycle: int, error: Optional[str] = None) -> None:
    """Write a health status file for external monitoring."""
    status = {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle,
        "status": "ok" if success else "error",
        "error": error,
    }
    try:
        HEALTH_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    except Exception:
        pass  # Non-critical

API_URL = "http://localhost:8000/api/v1/internal/update"

def _push_to_api(row: dict, strategy_dir: str, row_count: int) -> None:
    """Push the latest state to the backend API."""
    try:
        ts = row.get("Date-Time")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_iso = ts.isoformat()
        else:
            ts_iso = datetime.now(timezone.utc).isoformat()
            
        price = row.get("Price", 0.0)
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = 0.0
            
        signals_dict = {}
        for col in EXCEL_COLUMNS:
            if col not in ("Date-Time", "Price"):
                signals_dict[col] = str(row.get(col, "N/A"))

        payload = {
            "timestamp": ts_iso,
            "price": price,
            "direction": strategy_dir,
            "signals": signals_dict,
            "row_count": row_count
        }
        # Fire and forget with short timeout to avoid blocking
        requests.post(API_URL, json=payload, timeout=0.5)
    except Exception as e:
        log.debug(f"API push failed (is the backend running?): {e}")


def _print_dashboard(
    cycle: int,
    row: dict,
    file_path: Optional[Path],
    row_count: int,
    strategy_dir: str = "FLAT",
) -> None:
    """Print a compact live dashboard to the console."""
    ts = row.get("Date-Time", datetime.now())
    price = row.get("Price", "N/A")

    # Build signal summary line
    signals = []
    for col in EXCEL_COLUMNS:
        if col in ("Date-Time", "Price"):
            continue
        val = row.get(col, "N/A")
        signals.append(f"{col}={val}")

    ts_str = ts.strftime("%H:%M:%S") if isinstance(ts, datetime) else str(ts)
    price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else str(price)

    # Strategy direction indicator
    dir_icon = {"LONG": "▲ LONG", "SHORT": "▼ SHORT", "FLAT": "— FLAT"}.get(
        strategy_dir, "— FLAT"
    )

    print(
        f"\r| #{cycle:<5} | {ts_str} | {price_str:>12} | {dir_icon:<9} | "
        f"{' | '.join(signals)} | "
        f"File: {file_path.name if file_path else 'N/A'} ({row_count} rows) |",
        end="",
        flush=True,
    )


def main() -> None:
    """Run the pipeline loop."""
    global _shutdown_requested

    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print("=" * 80)
    print("  +----------------------------------------------------------+")
    print("  |   XAU/USD GOLD TRADING DATA PIPELINE                    |")
    print("  |   Real-time Technical Analysis -> Excel Database        |")
    print("  |   Rule-Based Strategy Engine: Active                    |")
    print("  |   InvestingPro: All 9 timeframes active                 |")
    print("  |   Press Ctrl+C to stop gracefully                      |")
    print("  +----------------------------------------------------------+")
    print(f"  |   Account: ${ACCOUNT_BALANCE:,.0f}  "
          f"Risk: {RISK_PER_TRADE_PCT*100:.1f}%/trade               |")
    print("  +----------------------------------------------------------+")
    print("=" * 80)

    scraper = GoldScraper()
    validator = DataValidator()
    storage = ExcelStorage()
    strategy = TradingStrategy()
    strategy.load_atr_state()

    cycle = 0
    consecutive_failures = 0
    last_success_time = time.time()

    try:
        # -- Launch browser + sign in -----------------------------------
        log.info("Starting pipeline...")
        scraper.start()
        log.info("Authenticated session active -- extracting all timeframes.")

        # ── Main loop ─────────────────────────────────────────────
        while not _shutdown_requested:
            cycle += 1
            cycle_start = time.time()

            try:
                # ── Step 1: Read DOM snapshot ─────────────────────
                raw = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        raw = scraper.read_snapshot()
                        break
                    except Exception as e:
                        delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                        log.warning(
                            f"Scrape attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        if attempt < MAX_RETRIES:
                            time.sleep(delay)

                if raw is None:
                    consecutive_failures += 1
                    log.error(f"All {MAX_RETRIES} scrape attempts failed. (streak: {consecutive_failures})")
                    _update_health(False, cycle, "All scrape attempts failed")

                    # Watchdog: if too many failures, force reload
                    if time.time() - last_success_time > WATCHDOG_TIMEOUT_SECONDS:
                        log.warning("Watchdog triggered — forcing browser reload...")
                        try:
                            scraper.force_reload()
                        except Exception as reload_err:
                            log.error(f"Watchdog reload failed: {reload_err}")
                            log.info("Attempting full browser restart...")
                            scraper.stop()
                            time.sleep(5)
                            scraper.start()
                        last_success_time = time.time()  # Reset timer

                    time.sleep(REFRESH_INTERVAL_SECONDS)
                    continue

                # ── Step 2: Parse ─────────────────────────────────
                row = parse_snapshot(raw)

                # ── Step 3: Validate ──────────────────────────────────
                is_valid, reason, corrections = validator.validate(row)

                # Apply any validator corrections (e.g. invalid signals → N/A)
                if corrections:
                    row.update(corrections)

                # ── Step 4: Strategy evaluation ───────────────────
                # Always evaluate (ATR needs every price tick), even
                # if the row will be skipped for storage.
                strategy_signal = strategy.evaluate(row)
                strategy_dir = "FLAT"

                if strategy_signal is not None:
                    strategy_dir = strategy_signal.direction
                    # Merge strategy output into the row for Excel
                    row.update(strategy_signal.to_row_dict())

                if not is_valid:
                    log.info(f"Row skipped: {reason}")
                    _update_health(True, cycle)
                    consecutive_failures = 0
                    last_success_time = time.time()
                else:
                    # ── Step 5: Store ─────────────────────────────
                    storage.append_row(row)
                    _update_health(True, cycle)
                    consecutive_failures = 0
                    last_success_time = time.time()

                # ── Dashboard ─────────────────────────────────────
                _print_dashboard(
                    cycle, row, storage.current_file, storage.row_count,
                    strategy_dir=strategy_dir,
                )
                
                # ── Push to API ───────────────────────────────────
                _push_to_api(row, strategy_dir, storage.row_count)

            except KeyboardInterrupt:
                _shutdown_requested = True
                break
            except Exception as e:
                consecutive_failures += 1
                log.error(f"Unexpected error in cycle #{cycle}: {e}", exc_info=True)
                _update_health(False, cycle, str(e))

            # ── Sleep for remaining interval ──────────────────────
            elapsed = time.time() - cycle_start
            sleep_time = max(0, REFRESH_INTERVAL_SECONDS - elapsed)
            if sleep_time > 0 and not _shutdown_requested:
                time.sleep(sleep_time)

    except Exception as e:
        log.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        # ── Graceful shutdown ─────────────────────────────────────
        print("\n")
        log.info("Shutting down pipeline...")
        strategy.save_atr_state()
        storage.flush()
        storage.close()
        scraper.stop()

        print("\n" + "=" * 80)
        print(f"  Pipeline stopped after {cycle} cycles.")
        if storage.current_file:
            print(f"  Data saved to: {storage.current_file}")
        print(f"  Total rows written today: {storage.row_count}")
        if strategy.last_signal:
            print(f"  Last strategy signal: {strategy.last_signal}")
        print("=" * 80)


if __name__ == "__main__":
    main()

