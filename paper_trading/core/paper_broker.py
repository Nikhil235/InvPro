"""
paper_broker.py -- Simulated broker engine for XAU/USD paper trading.

Handles order submission with realistic spread/slippage/commission,
position tracking, and SL/TP monitoring on every price tick.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from paper_trading.config.settings import (
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
    OrderType,
    make_event,
)
from core.database import Database
from core.clock import ClockService
from core.event_bus import EventBus
from core.events import ORDER_SUBMITTED, ORDER_FILLED, ORDER_CANCELLED, TRADE_CLOSED, POSITION_UPDATE
from paper_trading.core.account_ledger import AccountLedger
from paper_trading.utils.logger import get_logger

log = get_logger("broker")

class PaperBroker:
    """
    Simulated XAU/USD broker with spread, slippage, and commission.
    """

    def __init__(
        self,
        db: Database,
        clock: ClockService,
        event_bus: EventBus,
        ledger: AccountLedger,
        session_id: str
    ) -> None:
        self._db = db
        self._clock = clock
        self._event_bus = event_bus
        self._ledger = ledger
        self._session_id = session_id
        
        self._positions: Dict[int, Position] = {}
        self._pending_orders: Dict[int, OrderRequest] = {}
        
        self._load_state()

        log.info(f"Paper broker initialised for session {session_id}")

    def _load_state(self):
        """Load pending orders and active positions from DB."""
        orders = self._db.fetchall("SELECT * FROM orders WHERE session_id = ? AND status = 'PENDING'", (self._session_id,))
        for row in orders:
            req = OrderRequest.from_db_row(row)
            self._pending_orders[req.order_id] = req
            
        positions = self._db.fetchall("SELECT * FROM positions WHERE session_id = ?", (self._session_id,))
        for row in positions:
            pos = Position.from_db_row(row)
            self._positions[pos.position_id] = pos

    def submit_order(
        self,
        request: OrderRequest,
        fill_time: Optional[datetime] = None,
    ) -> Optional[Fill]:
        
        if fill_time is None:
            fill_time = self._clock.now()

        request.session_id = self._session_id
        
        sql = """
            INSERT INTO orders (
                side, order_type, status, requested_price, lots, stop_loss, take_profit,
                confidence, bias, risk_amount, reason, signal_time, created_at, session_id, strategy_blob,
                execution_mode, slippage_model, tp1, tp2, tp3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self._db.execute(sql, (
            request.side.value, request.order_type.value, request.status.value, request.requested_price,
            request.lots, request.stop_loss, request.take_profit, request.confidence, request.bias,
            request.risk_amount, request.reason, request.signal_time.isoformat(), fill_time.isoformat(),
            self._session_id, request.strategy_blob, request.execution_mode, request.slippage_model,
            request.tp1, request.tp2, request.tp3
        ))
        request.order_id = cursor.lastrowid
        
        self._event_bus.publish(ORDER_SUBMITTED, make_event(
            ORDER_SUBMITTED,
            order_id=request.order_id,
            side=request.side.value,
            order_type=request.order_type.value,
            price=request.requested_price,
            lots=request.lots,
            sl=request.stop_loss,
            tp=request.take_profit
        ))

        if request.order_type == OrderType.MARKET:
            return self._execute_fill(request, fill_time, request.requested_price)
        else:
            self._pending_orders[request.order_id] = request
            log.info(f"PENDING #{request.order_id}: {request.side.value} {request.order_type.value} @ {request.requested_price:,.2f}")
            return None

    def _execute_fill(self, request: OrderRequest, fill_time: datetime, current_market_price: float) -> Fill:
        spread = SPREAD_POINTS / 2.0
        
        is_replay = getattr(self._clock, "mode", getattr(self._clock, "_mode", "live")) == "replay"
        execution_mode = "replay" if is_replay else "live"
        
        if is_replay:
            slippage = (SLIPPAGE_POINTS / 2.0) * random.uniform(0.3, 1.7)
            slippage_model = "stochastic_replay"
            request.reason = f"{request.reason} [Replay: Stochastic Slippage]" if request.reason else "[Replay: Stochastic Slippage]"
        else:
            slippage = random.uniform(0, SLIPPAGE_POINTS) # Live simulation randomness
            slippage_model = "random_uniform"
            
        request.execution_mode = execution_mode
        request.slippage_model = slippage_model
        
        extra_slippage = 0.0
        if request.lots > 10:
            extra_slippage = ((request.lots - 10) // 5) * 0.5
            slippage += extra_slippage
            
        total_slippage_points = slippage

        if request.side == Side.LONG:
            fill_price = current_market_price + spread + slippage
            if request.order_type == OrderType.LIMIT:
                fill_price = min(fill_price, request.requested_price)
        else:
            fill_price = current_market_price - spread - slippage
            if request.order_type == OrderType.LIMIT:
                fill_price = max(fill_price, request.requested_price)

        fill_price = round(fill_price, 2)

        entry_commission = (COMMISSION_PER_LOT / 2.0) * request.lots
        self._ledger.debit(entry_commission, "Entry Commission")

        sql = """
            INSERT INTO positions (
                order_id, side, entry_price, fill_price, stop_loss, take_profit,
                lots, confidence, bias, risk_amount, reason, open_time, session_id, strategy_blob,
                execution_mode, slippage_model, slippage_points_applied,
                tp1, tp2, tp3, tp1_hit, tp2_hit, tp3_hit, realised_pnl, initial_lots, initial_sl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self._db.execute(sql, (
            request.order_id, request.side.value, request.requested_price, fill_price,
            request.stop_loss, request.take_profit, request.lots, request.confidence,
            request.bias, request.risk_amount, request.reason, fill_time.isoformat(), self._session_id, request.strategy_blob,
            execution_mode, slippage_model, total_slippage_points,
            request.tp1, request.tp2, request.tp3, 0, 0, 0, 0.0, request.lots, request.stop_loss
        ))
        pos_id = cursor.lastrowid
        
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
            tp1=request.tp1,
            tp2=request.tp2,
            tp3=request.tp3,
            tp1_hit=False,
            tp2_hit=False,
            tp3_hit=False,
            realised_pnl=0.0,
            initial_lots=request.lots,
            initial_sl=request.stop_loss,
            session_id=self._session_id,
            reason=request.reason,
            strategy_blob=request.strategy_blob,
            execution_mode=execution_mode,
            slippage_model=slippage_model,
            slippage_points_applied=total_slippage_points
        )
        self._positions[pos_id] = position

        self._db.execute("""
            UPDATE orders SET status = 'FILLED', fill_price = ?, spread_cost = ?, 
            slippage_cost = ?, filled_at = ? WHERE order_id = ?
        """, (fill_price, spread, slippage, fill_time.isoformat(), request.order_id))

        fill = Fill(
            order_id=request.order_id,
            fill_price=fill_price,
            spread_cost=spread,
            slippage=slippage,
            fill_time=fill_time,
            status=OrderStatus.FILLED,
        )

        delta = abs(fill_price - request.requested_price)
        log.info(
            f"FILLED #{request.order_id}: {request.side.value} "
            f"{request.lots:.4f} lots @ {fill_price:,.2f} "
            f"(req: {request.requested_price:,.2f}, delta: {delta:.2f})"
        )

        self._event_bus.publish(ORDER_FILLED, make_event(
            ORDER_FILLED,
            order_id=request.order_id,
            position_id=pos_id,
            side=request.side.value,
            fill_price=fill_price,
            advisory_price=request.requested_price,
            price_delta=round(delta, 2),
            spread=round(spread, 2),
            slippage=round(slippage, 2),
            lots=request.lots,
            sl=request.stop_loss,
            tp=request.take_profit,
            tp1=request.tp1,
            tp2=request.tp2,
            tp3=request.tp3,
            tp1_hit=0,
            tp2_hit=0,
            tp3_hit=0,
            realised_pnl=0.0,
            initial_lots=request.lots,
        ))
        return fill

    def tick(
        self,
        price: float,
        timestamp: Optional[datetime] = None,
    ) -> List[ClosedTrade]:
        if timestamp is None:
            timestamp = self._clock.now()

        for order_id, req in list(self._pending_orders.items()):
            should_fill = False
            if req.order_type == OrderType.LIMIT:
                if req.side == Side.LONG and (price + SPREAD_POINTS / 2.0) <= req.requested_price:
                    should_fill = True
                elif req.side == Side.SHORT and (price - SPREAD_POINTS / 2.0) >= req.requested_price:
                    should_fill = True
            elif req.order_type == OrderType.STOP:
                if req.side == Side.LONG and (price + SPREAD_POINTS / 2.0) >= req.requested_price:
                    should_fill = True
                elif req.side == Side.SHORT and (price - SPREAD_POINTS / 2.0) <= req.requested_price:
                    should_fill = True
            
            if should_fill:
                self._execute_fill(req, timestamp, price)
                del self._pending_orders[order_id]

        closed_this_tick: List[ClosedTrade] = []

        for pos_id, pos in list(self._positions.items()):
            pos.update_pnl(price, LOT_SIZE)
            
            # Save current price and pnl to DB
            self._db.execute("UPDATE positions SET current_price = ?, unrealised_pnl = ? WHERE position_id = ?", (price, pos.unrealised_pnl, pos_id))

            # 1. Check if SL is hit first
            is_sl_hit = False
            if pos.side == Side.LONG:
                if price <= pos.stop_loss:
                    is_sl_hit = True
            else:
                if price >= pos.stop_loss:
                    is_sl_hit = True

            if is_sl_hit:
                # Apply slippage and spread penalty for SL (market execution)
                penalty = SLIPPAGE_POINTS + SPREAD_POINTS
                exit_price = price - penalty if pos.side == Side.LONG else price + penalty
                
                # Strong validation on exit_price
                import math
                if exit_price is None or not isinstance(exit_price, (int, float)) or not math.isfinite(exit_price) or exit_price <= 0:
                    exit_price = pos.fill_price

                trade = self._close_position(pos_id, exit_price, timestamp, ExitReason.SL_HIT)
                if trade is not None:
                    closed_this_tick.append(trade)
                continue

            # 2. Check partial take-profit levels if tp1 is set
            if pos.tp1 is not None:
                # Evaluate TP levels sequentially and idempotently
                if not pos.tp1_hit:
                    is_tp1_hit = False
                    if pos.side == Side.LONG:
                        if price >= pos.tp1:
                            is_tp1_hit = True
                    else:
                        if price <= pos.tp1:
                            is_tp1_hit = True

                    if is_tp1_hit:
                        pos.tp1_hit = True
                        tp1_lots = round(pos.initial_lots / 3.0, 4)
                        exit_price = pos.tp1
                        
                        # Apply SL breakeven
                        pos.stop_loss = pos.fill_price
                        
                        trade = self._close_position(pos_id, exit_price, timestamp, ExitReason.TP1_HIT, lots_to_close=tp1_lots)
                        if trade is not None:
                            closed_this_tick.append(trade)
                        continue

                elif not pos.tp2_hit:
                    is_tp2_hit = False
                    if pos.side == Side.LONG:
                        if price >= pos.tp2:
                            is_tp2_hit = True
                    else:
                        if price <= pos.tp2:
                            is_tp2_hit = True

                    if is_tp2_hit:
                        pos.tp2_hit = True
                        tp2_lots = round(pos.initial_lots / 3.0, 4)
                        exit_price = pos.tp2
                        
                        trade = self._close_position(pos_id, exit_price, timestamp, ExitReason.TP2_HIT, lots_to_close=tp2_lots)
                        if trade is not None:
                            closed_this_tick.append(trade)
                        continue

                elif not pos.tp3_hit:
                    is_tp3_hit = False
                    if pos.side == Side.LONG:
                        if price >= pos.tp3:
                            is_tp3_hit = True
                    else:
                        if price <= pos.tp3:
                            is_tp3_hit = True

                    if is_tp3_hit:
                        pos.tp3_hit = True
                        exit_price = pos.tp3
                        
                        trade = self._close_position(pos_id, exit_price, timestamp, ExitReason.TP3_HIT, lots_to_close=pos.lots)
                        if trade is not None:
                            closed_this_tick.append(trade)
                        continue

                # Handle Trailing SL if TP2 is hit and trade remains open
                if pos.tp2_hit:
                    risk_sl = pos.initial_sl if pos.initial_sl is not None else pos.fill_price
                    stop_distance = abs(pos.fill_price - risk_sl)
                    if pos.side == Side.LONG:
                        new_sl = round(price - stop_distance, 2)
                        if new_sl > pos.stop_loss:
                            pos.stop_loss = new_sl
                            self._db.execute("UPDATE positions SET stop_loss = ? WHERE position_id = ?", (new_sl, pos_id))
                    else:
                        new_sl = round(price + stop_distance, 2)
                        if new_sl < pos.stop_loss:
                            pos.stop_loss = new_sl
                            self._db.execute("UPDATE positions SET stop_loss = ? WHERE position_id = ?", (new_sl, pos_id))

            else:
                # Legacy full exit check
                exit_reason = pos.check_sl_tp(price)
                if exit_reason is not None:
                    exit_price = price
                    if exit_reason == ExitReason.SL_HIT:
                        penalty = SLIPPAGE_POINTS + SPREAD_POINTS
                        exit_price = price - penalty if pos.side == Side.LONG else price + penalty
                    elif exit_reason == ExitReason.TP_HIT:
                        if pos.side == Side.LONG:
                            exit_price = max(pos.take_profit, price)
                        else:
                            exit_price = min(pos.take_profit, price)

                    # Ensure exit_price is a valid finite float > 0
                    import math
                    if exit_price is None or not isinstance(exit_price, (int, float)) or not math.isfinite(exit_price) or exit_price <= 0:
                        exit_price = pos.fill_price

                    trade = self._close_position(pos_id, exit_price, timestamp, exit_reason)
                    if trade is not None:
                        closed_this_tick.append(trade)

        # Recalculate total unrealised PnL for active positions
        total_unrealised_pnl = sum(p.unrealised_pnl for p in self._positions.values())
        self._ledger.update_equity(total_unrealised_pnl, len(self._positions))

        # Position update event
        if self._positions:
            pos_payloads = [
                {
                    "position_id": p.position_id,
                    "unrealised_pnl": p.unrealised_pnl,
                    "current_price": p.current_price,
                    "lots": p.lots,
                    "stop_loss": p.stop_loss,
                    "tp1_hit": p.tp1_hit,
                    "tp2_hit": p.tp2_hit,
                    "tp3_hit": p.tp3_hit,
                    "realised_pnl": p.realised_pnl,
                }
                for p in self._positions.values()
            ]
            self._event_bus.publish(POSITION_UPDATE, make_event(POSITION_UPDATE, positions=pos_payloads, total_unrealised_pnl=total_unrealised_pnl))

        return closed_this_tick

    def close_position(
        self,
        position_id: int,
        price: float,
        timestamp: Optional[datetime] = None,
        reason: ExitReason = ExitReason.SIGNAL_REVERSAL,
    ) -> Optional[ClosedTrade]:
        if timestamp is None:
            timestamp = self._clock.now()
            
        pos = self._positions.get(position_id)
        if pos:
            import math
            if price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                price = pos.fill_price
                
        return self._close_position(position_id, price, timestamp, reason)

    def close_all_positions(
        self,
        price: float,
        timestamp: Optional[datetime] = None,
        reason: ExitReason = ExitReason.END_OF_SESSION,
    ) -> List[ClosedTrade]:
        if timestamp is None:
            timestamp = self._clock.now()
        closed = []
        for pos_id in list(self._positions.keys()):
            pos = self._positions.get(pos_id)
            pos_price = price
            if pos:
                import math
                if pos_price is None or not isinstance(pos_price, (int, float)) or not math.isfinite(pos_price) or pos_price <= 0:
                    pos_price = pos.fill_price
            trade = self._close_position(pos_id, pos_price, timestamp, reason)
            if trade:
                closed.append(trade)
        return closed

    def cancel_order(self, order_id: int) -> bool:
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
            self._db.execute("UPDATE orders SET status = 'CANCELLED', cancelled_at = ? WHERE order_id = ?", (self._clock.now().isoformat(), order_id))
            self._event_bus.publish(ORDER_CANCELLED, make_event("ORDER_CANCELLED", order_id=order_id))
            return True
        return False

    def _close_position(
        self,
        position_id: int,
        exit_price: float,
        timestamp: datetime,
        reason: ExitReason,
        lots_to_close: Optional[float] = None,
    ) -> Optional[ClosedTrade]:
        import math
        # 1. Prevent any trade from being saved if exit_price is not a valid finite number or <= 0
        if exit_price is None or not isinstance(exit_price, (int, float)) or not math.isfinite(exit_price) or exit_price <= 0:
            log.error(f"Cannot close position #{position_id}: invalid exit price {exit_price}")
            return None

        # 2. Guard: Ensure position exists
        pos = self._positions.get(position_id)
        if pos is None:
            log.warning(f"Position #{position_id} not found or already closed")
            return None

        close_lots = lots_to_close if (lots_to_close is not None and lots_to_close < pos.lots) else pos.lots
        is_full_close = (close_lots >= pos.lots)

        if is_full_close:
            self._positions.pop(position_id, None)

        exit_price = round(exit_price, 2)

        if pos.side == Side.LONG:
            gross_pnl = (exit_price - pos.fill_price) * close_lots * LOT_SIZE
        else:
            gross_pnl = (pos.fill_price - exit_price) * close_lots * LOT_SIZE

        exit_commission = (COMMISSION_PER_LOT / 2.0) * close_lots
        total_commission = COMMISSION_PER_LOT * close_lots
        net_pnl = gross_pnl - total_commission

        self._ledger.debit(exit_commission, "Exit Commission")
        if gross_pnl > 0:
            self._ledger.credit(gross_pnl, f"Profit {pos.side.value}")
        else:
            self._ledger.debit(abs(gross_pnl), f"Loss {pos.side.value}")

        risk_sl = pos.initial_sl if pos.initial_sl is not None else pos.stop_loss
        if pos.side == Side.LONG:
            risk_dist = pos.fill_price - risk_sl
            reward_dist = exit_price - pos.fill_price
        else:
            risk_dist = risk_sl - pos.fill_price
            reward_dist = pos.fill_price - exit_price

        rr_achieved = (reward_dist / risk_dist) if risk_dist > 0 else 0.0

        # Insert to trades table
        sql = """
            INSERT INTO trades (
                order_id, position_id, side, entry_price, fill_price, exit_price,
                stop_loss, take_profit, lots, open_time, close_time, exit_reason,
                gross_pnl, commission, net_pnl, risk_amount, rr_achieved,
                confidence, bias, balance_after, reason, session_id, strategy_blob,
                execution_mode, slippage_model, slippage_points_applied, tp1, tp2, tp3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self._db.execute(sql, (
            pos.order_id, position_id, pos.side.value, pos.entry_price, pos.fill_price, exit_price,
            pos.stop_loss, pos.take_profit, close_lots, pos.open_time.isoformat(), timestamp.isoformat(),
            reason.value, round(gross_pnl, 2), round(total_commission, 2), round(net_pnl, 2),
            pos.risk_amount, round(rr_achieved, 2), pos.confidence, pos.bias,
            round(self._ledger.balance, 2), pos.reason, self._session_id, pos.strategy_blob,
            pos.execution_mode, pos.slippage_model, pos.slippage_points_applied,
            pos.tp1, pos.tp2, pos.tp3
        ))
        
        trade_id = cursor.lastrowid
        
        if is_full_close:
            self._db.execute("DELETE FROM positions WHERE position_id = ?", (position_id,))
        else:
            pos.lots = round(pos.lots - close_lots, 4)
            pos.realised_pnl = round(pos.realised_pnl + net_pnl, 2)
            self._db.execute("""
                UPDATE positions 
                SET lots = ?, realised_pnl = ?, tp1_hit = ?, tp2_hit = ?, tp3_hit = ?, stop_loss = ?
                WHERE position_id = ?
            """, (pos.lots, pos.realised_pnl, 1 if pos.tp1_hit else 0, 1 if pos.tp2_hit else 0, 1 if pos.tp3_hit else 0, pos.stop_loss, position_id))

        trade = ClosedTrade(
            trade_id=trade_id,
            order_id=pos.order_id,
            position_id=position_id,
            side=pos.side,
            entry_price=pos.entry_price,
            fill_price=pos.fill_price,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            exit_price=exit_price,
            lots=close_lots,
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
            balance_after=round(self._ledger.balance, 2),
            reason=pos.reason,
            session_id=self._session_id,
            strategy_blob=pos.strategy_blob,
            execution_mode=pos.execution_mode,
            slippage_model=pos.slippage_model,
            slippage_points_applied=pos.slippage_points_applied,
            tp1=pos.tp1,
            tp2=pos.tp2,
            tp3=pos.tp3
        )

        result_str = "WIN" if trade.is_winner else "LOSS"
        log.info(
            f"CLOSED Leg #{trade.trade_id}: {pos.side.value} "
            f"{close_lots:.4f} lots ({'FULL' if is_full_close else 'PARTIAL'}), {reason.value}, "
            f"entry={pos.fill_price:,.2f} -> exit={exit_price:,.2f}, "
            f"P&L=${net_pnl:,.2f} ({result_str}), "
            f"R:R={rr_achieved:.2f}, balance=${self._ledger.balance:,.2f}"
        )

        self._event_bus.publish(TRADE_CLOSED, make_event(
            TRADE_CLOSED,
            trade_id=trade.trade_id,
            order_id=pos.order_id,
            position_id=position_id,
            side=pos.side.value,
            fill_price=pos.fill_price,
            exit_price=exit_price,
            exit_reason=reason.value,
            lots=close_lots,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            commission=round(total_commission, 2),
            rr_achieved=round(rr_achieved, 2),
            balance_after=round(self._ledger.balance, 2),
            reason=pos.reason,
            is_full_close=is_full_close
        ))

        return trade

    @property
    def balance(self) -> float:
        return self._ledger.balance

    @property
    def equity(self) -> float:
        return self._ledger.equity

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def open_position_count(self) -> int:
        return len(self._positions)

    @property
    def closed_trades(self) -> List[ClosedTrade]:
        """Fetch all closed trades for the current session from DB."""
        rows = self._db.fetchall("SELECT * FROM trades WHERE session_id = ? ORDER BY close_time ASC", (self._session_id,))
        return [ClosedTrade.from_db_row(row) for row in rows]
