"""
journal.py -- Trade journal with triple-format persistence (CSV, Excel, JSON).

Records every trade and event to disk for post-session analysis.
All output files are written to ``paper_trading/output/``.

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from paper_trading.config.settings import OUTPUT_DIR
from paper_trading.core.order_manager import ClosedTrade, RejectedOrder
from paper_trading.utils.logger import get_logger

log = get_logger("journal")

# ── CSV column order ──────────────────────────────────────────────────
_CSV_COLUMNS = [
    "trade_id",
    "side",
    "open_time",
    "close_time",
    "entry_price",
    "fill_price",
    "exit_price",
    "stop_loss",
    "take_profit",
    "exit_reason",
    "lots",
    "gross_pnl",
    "commission",
    "net_pnl",
    "risk_amount",
    "rr_achieved",
    "confidence",
    "bias",
    "balance_after",
    "reason",
]


class TradeJournal:
    """
    Writes trade records to CSV, Excel, and JSON event log files.

    Files are named with the current date and written to OUTPUT_DIR:
        journal_YYYY-MM-DD.csv
        journal_YYYY-MM-DD.xlsx
        events_YYYY-MM-DD.jsonl
    """

    def __init__(self, session_date: Optional[date] = None) -> None:
        self._date = session_date or date.today()
        date_str = self._date.strftime("%Y-%m-%d")

        self._csv_path = OUTPUT_DIR / f"journal_{date_str}.csv"
        self._xlsx_path = OUTPUT_DIR / f"journal_{date_str}.xlsx"
        self._jsonl_path = OUTPUT_DIR / f"events_{date_str}.jsonl"

        self._trades: List[ClosedTrade] = []
        self._events: List[Dict[str, Any]] = []
        self._csv_initialised = False

        log.info(
            f"Journal initialised: "
            f"CSV={self._csv_path.name}, "
            f"JSONL={self._jsonl_path.name}"
        )

    # ── Public API ────────────────────────────────────────────────

    def record_trade(self, trade: ClosedTrade) -> None:
        """Record a closed trade to memory and append to CSV."""
        self._trades.append(trade)
        self._append_csv(trade)
        self._append_jsonl({
            "type": "TRADE_RECORD",
            "timestamp": datetime.now().isoformat(),
            **trade.to_dict(),
        })
        log.debug(f"Trade #{trade.trade_id} recorded to journal")

    def record_event(self, event: Dict[str, Any]) -> None:
        """Record an arbitrary event to the JSON event log."""
        self._events.append(event)
        self._append_jsonl(event)

    def record_rejection(self, rejection: RejectedOrder) -> None:
        """Record a rejected order to the event log."""
        event = {
            "type": "ORDER_REJECTED",
            "timestamp": datetime.now().isoformat(),
            **rejection.to_dict(),
        }
        self._events.append(event)
        self._append_jsonl(event)

    def flush_excel(self) -> None:
        """
        Write all accumulated trades to an Excel file with styling.

        Called at the end of a session to produce the final journal.
        """
        if not self._trades:
            log.info("No trades to write to Excel journal.")
            return

        try:
            import pandas as pd
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            # Build DataFrame
            rows = [t.to_dict() for t in self._trades]
            df = pd.DataFrame(rows)

            # Reorder columns
            available = [c for c in _CSV_COLUMNS if c in df.columns]
            extra = [c for c in df.columns if c not in _CSV_COLUMNS]
            df = df[available + extra]

            # Write to Excel with openpyxl for styling
            wb = Workbook()
            ws = wb.active
            ws.title = "Trade_Journal"

            # Header
            header_font = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
            header_fill = PatternFill(
                start_color="2C3E50", end_color="2C3E50", fill_type="solid"
            )
            for col_idx, col_name in enumerate(df.columns, start=1):
                cell = ws.cell(row=1, column=col_idx, value=col_name)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
                ws.column_dimensions[get_column_letter(col_idx)].width = max(
                    len(str(col_name)) + 4, 14
                )

            # Data rows
            win_fill = PatternFill(
                start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"
            )
            loss_fill = PatternFill(
                start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"
            )

            for row_idx, (_, row) in enumerate(df.iterrows(), start=2):
                for col_idx, val in enumerate(row, start=1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.alignment = Alignment(horizontal="center")

                # Colour entire row by P&L
                net_pnl = row.get("net_pnl", 0)
                fill = win_fill if net_pnl > 0 else loss_fill
                for col_idx in range(1, len(df.columns) + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = fill

            # Freeze header
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(len(df.columns))}1"

            wb.save(str(self._xlsx_path))
            log.info(
                f"Excel journal saved: {self._xlsx_path.name} "
                f"({len(self._trades)} trades)"
            )

        except ImportError as e:
            log.warning(f"Could not write Excel journal (missing dependency): {e}")
        except Exception as e:
            log.error(f"Error writing Excel journal: {e}")

    # ── Getters ───────────────────────────────────────────────────

    @property
    def trades(self) -> List[ClosedTrade]:
        return self._trades

    @property
    def csv_path(self) -> Path:
        return self._csv_path

    @property
    def xlsx_path(self) -> Path:
        return self._xlsx_path

    @property
    def jsonl_path(self) -> Path:
        return self._jsonl_path

    # ── Private ───────────────────────────────────────────────────

    def _append_csv(self, trade: ClosedTrade) -> None:
        """Append a single trade row to the CSV file."""
        try:
            write_header = not self._csv_initialised or not self._csv_path.exists()
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
                if write_header:
                    writer.writeheader()
                    self._csv_initialised = True
                writer.writerow(trade.to_dict())
        except Exception as e:
            log.error(f"Error appending to CSV: {e}")

    def _append_jsonl(self, event: Dict[str, Any]) -> None:
        """Append a single JSON event to the JSONL file."""
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as e:
            log.error(f"Error appending to JSONL: {e}")
