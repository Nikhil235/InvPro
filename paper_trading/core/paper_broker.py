"""
paper_broker.py -- Simulated broker engine for XAU/USD paper trading.

Handles order submission with realistic spread/slippage/commission,
position tracking, and SL/TP monitoring on every price tick.

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import itertools
import random
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from paper_trading.config.settings import (
    INITIAL_CAPITAL,
    SPREAD_POINTS,
    SLIPPAGE_POINTS,
    COMMISSION_PER_LOT,
    LOT_SIZE,
)
from paper_trading.core.order_manager import (
    OrderRequest,
    Fill,
    Position,
    ClosedTrade,
    ExitReason,
    OrderStatus,
    Side,
    make_event,
    _trade_counter,
)
from paper_trading.utils.logger import get_logger

log = get_logger("broker")

_position_counter = itertools.count(1)


class PaperBroker:
    """
    Simulated XAU/USD broker with spread, slippage, and commission.

    Usage:
        broker = PaperBroker()
        fill = broker.submit_order(order_request)
        closed_trades = broker.tick(current_price, timestamp)
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        on_trade_closed: Optional[Callable[[ClosedTrade], None]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self._balance = initial_capital
        self._initial_capital = initial_capital
        self._positions: Dict[int, Position] = {}
        self._closed_trades: List[ClosedTrade] = []
        self._on_trade_closed = on_trade_closed
        self._on_event = on_event

        log.info(f"Paper broker initialised: capital=${initial_capital:,.2f}")

    # ── Order submission ──────────────────────────────────────────

    def submit_order(
        self,
        request: OrderRequest,
        fill_time: Optional[datetime] = None,
    ) -> Fill:
        """
        Simulate filling a market order with spread + slippage.

        Returns a Fill object with the actual execution price.
        """
        if fill_time is None:
            fill_time = datetime.now()

        # Compute fill price
        spread = SPREAD_POINTS / 2.0
        slippage = random.uniform(0, SLIPPAGE_POINTS)

        if request.side == Side.LONG:
            # Longs fill at the ask (price + spread + slippage)
            fill_price = request.requested_price + spread + slippage
        else:
            # Shorts fill at the bid (price - spread - slippage)
            fill_price = request.requested_price - spread - slippage

        fill_price = round(fill_price, 2)

        # Charge half commission on entry
        entry_commission = (COMMISSION_PER_LOT / 2.0) * request.lots
        self._balance -= entry_commission

        # Create position
        pos_id = next(_position_counter)
        position = Position(
            position_id=pos_id,
            order_id=request.order_id,
            side=request.side,
            entry_price=request.requested_price,
            fill_price=fill_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            lots=request.lots,
            open_time=fill_time,
            confidence=request.confidence,
            bias=request.bias,
            risk_amount=request.risk_amount,
            reason=request.reason,
        )
        self._positions[pos_id] = position

        fill = Fill(
            order_id=request.order_id,
            fill_price=fill_price,
            spread_cost=spread,
            slippage=slippage,
            fill_time=fill_time,
            status=OrderStatus.FILLED,
        )

        # Validation: log price delta
        delta = abs(fill_price - request.requested_price)
        log.info(
            f"FILLED #{request.order_id}: {request.side.value} "
            f"{request.lots:.4f} lots @ {fill_price:,.2f} "
            f"(advisory: {request.requested_price:,.2f}, "
            f"delta: {delta:.2f}, spread: {spread:.2f}, slip: {slippage:.2f})"
        )

        self._emit_event(make_event(
            "ORDER_FILLED",
            order_id=request.order_id,
            position_id=pos_id,
            side=request.side,
            fill_price=fill_price,
            advisory_price=request.requested_price,
            price_delta=round(delta, 2),
            spread=round(spread, 2),
            slippage=round(slippage, 2),
            lots=request.lots,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        ))

        return fill

    # ── Price tick processing ─────────────────────────────────────

    def tick(
        self,
        price: float,
        timestamp: Optional[datetime] = None,
    ) -> List[ClosedTrade]:
        """
        Process a price tick: update P&L and check SL/TP on all positions.

        Returns a list of any trades that were closed on this tick.
        """
        if timestamp is None:
            timestamp = datetime.now()

        closed_this_tick: List[ClosedTrade] = []

        # Iterate over a copy since we may modify the dict
        for pos_id, pos in list(self._positions.items()):
            pos.update_pnl(price, LOT_SIZE)
            exit_reason = pos.check_sl_tp(price)

            if exit_reason is not None:
                # Determine exit price (SL or TP)
                if exit_reason == ExitReason.SL_HIT:
                    exit_price = pos.stop_loss
                elif exit_reason == ExitReason.TP_HIT:
                    exit_price = pos.take_profit
                else:
                    exit_price = price

                trade = self._close_position(pos_id, exit_price, timestamp, exit_reason)
                if trade is not None:
                    closed_this_tick.append(trade)

        return closed_this_tick

    # ── Position management ───────────────────────────────────────

    def close_position(
        self,
        position_id: int,
        price: float,
        timestamp: Optional[datetime] = None,
        reason: ExitReason = ExitReason.SIGNAL_REVERSAL,
    ) -> Optional[ClosedTrade]:
        """Manually close a position (e.g. on signal reversal)."""
        if timestamp is None:
            timestamp = datetime.now()
        return self._close_position(position_id, price, timestamp, reason)

    def close_all_positions(
        self,
        price: float,
        timestamp: Optional[datetime] = None,
        reason: ExitReason = ExitReason.END_OF_SESSION,
    ) -> List[ClosedTrade]:
        """Close all open positions (e.g. at end of session/replay)."""
        if timestamp is None:
            timestamp = datetime.now()
        closed = []
        for pos_id in list(self._positions.keys()):
            trade = self._close_position(pos_id, price, timestamp, reason)
            if trade:
                closed.append(trade)
        return closed

    # ── Getters ───────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def equity(self) -> float:
        """Balance + unrealised P&L on open positions."""
        return self._balance + sum(
            p.unrealised_pnl for p in self._positions.values()
        )

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def open_position_count(self) -> int:
        return len(self._positions)

    @property
    def closed_trades(self) -> List[ClosedTrade]:
        return self._closed_trades

    @property
    def initial_capital(self) -> float:
        return self._initial_capital

    # ── Private ───────────────────────────────────────────────────

    def _close_position(
        self,
        position_id: int,
        exit_price: float,
        timestamp: datetime,
        reason: ExitReason,
    ) -> Optional[ClosedTrade]:
        """Close a position, compute P&L, and record the trade."""
        pos = self._positions.pop(position_id, None)
        if pos is None:
            log.warning(f"Position #{position_id} not found for close")
            return None

        exit_price = round(exit_price, 2)

        # Compute gross P&L
        if pos.side == Side.LONG:
            gross_pnl = (exit_price - pos.fill_price) * pos.lots * LOT_SIZE
        else:
            gross_pnl = (pos.fill_price - exit_price) * pos.lots * LOT_SIZE

        # Charge remaining half commission on exit
        exit_commission = (COMMISSION_PER_LOT / 2.0) * pos.lots
        total_commission = COMMISSION_PER_LOT * pos.lots
        net_pnl = gross_pnl - exit_commission

        # Update balance
        self._balance += gross_pnl - exit_commission

        # Compute achieved R:R
        if pos.side == Side.LONG:
            risk_dist = pos.fill_price - pos.stop_loss
            reward_dist = exit_price - pos.fill_price
        else:
            risk_dist = pos.stop_loss - pos.fill_price
            reward_dist = pos.fill_price - exit_price

        rr_achieved = (reward_dist / risk_dist) if risk_dist > 0 else 0.0

        trade = ClosedTrade(
            trade_id=next(_trade_counter),
            order_id=pos.order_id,
            position_id=position_id,
            side=pos.side,
            entry_price=pos.entry_price,
            fill_price=pos.fill_price,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            exit_price=exit_price,
            lots=pos.lots,
            open_time=pos.open_time,
            close_time=timestamp,
            exit_reason=reason,
            gross_pnl=round(gross_pnl, 2),
            commission=round(total_commission, 2),
            net_pnl=round(net_pnl, 2),
            risk_amount=pos.risk_amount,
            rr_achieved=round(rr_achieved, 2),
            confidence=pos.confidence,
            bias=pos.bias,
            balance_after=round(self._balance, 2),
            reason=pos.reason,
        )

        self._closed_trades.append(trade)

        # Log
        result_str = "WIN" if trade.is_winner else "LOSS"
        log.info(
            f"CLOSED #{trade.trade_id}: {pos.side.value} "
            f"{pos.lots:.4f} lots, {reason.value}, "
            f"entry={pos.fill_price:,.2f} -> exit={exit_price:,.2f}, "
            f"P&L=${net_pnl:,.2f} ({result_str}), "
            f"R:R={rr_achieved:.2f}, balance=${self._balance:,.2f}"
        )

        # Emit event
        self._emit_event(make_event(
            "TRADE_CLOSED",
            trade_id=trade.trade_id,
            order_id=pos.order_id,
            side=pos.side,
            fill_price=pos.fill_price,
            exit_price=exit_price,
            exit_reason=reason,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            commission=round(total_commission, 2),
            rr_achieved=round(rr_achieved, 2),
            balance_after=round(self._balance, 2),
        ))

        # Callback
        if self._on_trade_closed:
            self._on_trade_closed(trade)

        return trade

    def _emit_event(self, event: Dict[str, Any]) -> None:
        """Send an event to the registered callback."""
        if self._on_event:
            self._on_event(event)
