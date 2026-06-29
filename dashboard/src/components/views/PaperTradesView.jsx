import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Briefcase, ArrowRightLeft, X } from 'lucide-react';
import { useFetch } from '../../hooks/useFetch';
import { useLiveData } from '../../contexts/LiveDataContext';
import { API_BASE_URL } from '../../config';
import { toast } from 'sonner';

export function PaperTradesView() {
  const { lastBrokerEvent, activeSessionId } = useLiveData() || {};
  const { data: fetchedPositions, loading: positionsLoading } = useFetch(activeSessionId ? `${API_BASE_URL}/api/positions?session_id=${activeSessionId}` : null);
  const { data: fetchedPendingOrders, loading: pendingLoading } = useFetch(activeSessionId ? `${API_BASE_URL}/api/orders/pending?session_id=${activeSessionId}` : null);
  
  const [activePositions, setActivePositions] = useState([]);
  const [pendingOrders, setPendingOrders] = useState([]);

  useEffect(() => {
    if (fetchedPositions) setActivePositions(fetchedPositions);
  }, [fetchedPositions]);

  useEffect(() => {
    if (fetchedPendingOrders) setPendingOrders(fetchedPendingOrders);
  }, [fetchedPendingOrders]);

  // Clear if session ends
  useEffect(() => {
    if (!activeSessionId) {
        setActivePositions([]);
        setPendingOrders([]);
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!lastBrokerEvent) return;
    
    const { event, data: payload } = lastBrokerEvent;

    if (event === 'ORDER_FILLED') {
      const pos = {
        position_id: payload.position_id,
        order_id: payload.order_id,
        side: payload.side?.value || payload.side,
        entry_price: payload.fill_price,
        lots: payload.lots,
        unrealised_pnl: 0.0,
        tp1: payload.tp1,
        tp2: payload.tp2,
        tp3: payload.tp3,
        tp1_hit: false,
        tp2_hit: false,
        tp3_hit: false,
        realised_pnl: 0.0,
        initial_lots: payload.initial_lots || payload.lots,
        stop_loss: payload.sl || payload.stop_loss
      };
      setActivePositions(prev => [pos, ...prev]);
      setPendingOrders(prev => prev.filter(o => o.order_id !== payload.order_id));
    } else if (event === 'TRADE_CLOSED') {
      const isFull = payload.is_full_close !== undefined ? payload.is_full_close : true;
      if (isFull) {
        setActivePositions(prev => prev.filter(p => p.position_id !== payload.position_id));
      }
    } else if (event === 'POSITION_UPDATE') {
      setActivePositions(prev => {
        const updateMap = new Map();
        payload.positions?.forEach(p => {
          updateMap.set(p.id || p.position_id, p);
        });
        
        return prev.map(pos => {
          const match = updateMap.get(pos.position_id);
          if (match) {
            return { 
              ...pos, 
              unrealised_pnl: match.unrealised_pnl,
              lots: match.lots !== undefined ? match.lots : pos.lots,
              stop_loss: match.stop_loss !== undefined ? match.stop_loss : pos.stop_loss,
              tp1_hit: match.tp1_hit !== undefined ? match.tp1_hit : pos.tp1_hit,
              tp2_hit: match.tp2_hit !== undefined ? match.tp2_hit : pos.tp2_hit,
              tp3_hit: match.tp3_hit !== undefined ? match.tp3_hit : pos.tp3_hit,
              realised_pnl: match.realised_pnl !== undefined ? match.realised_pnl : pos.realised_pnl
            };
          }
          return pos;
        });
      });
    } else if (event === 'ORDER_PENDING') {
       const order = {
          order_id: payload.order_id,
          side: payload.side?.value || payload.side,
          type: payload.order_type,
          requested_price: payload.requested_price,
          lots: payload.lots,
       };
       setPendingOrders(prev => [order, ...prev]);
    } else if (event === 'ORDER_CANCELLED') {
       setPendingOrders(prev => prev.filter(o => o.order_id !== payload.order_id));
    }
  }, [lastBrokerEvent]);

  const handleCancelOrder = async (orderId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/orders/${orderId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setPendingOrders(prev => prev.filter(o => o.order_id !== orderId));
        toast.info("Order Cancelled");
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to cancel order");
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Paper Trades</h1>
        <p className="text-secondary">Manage active positions and pending orders in the simulated broker environment.</p>
      </div>

      {!activeSessionId ? (
        <div className="flex flex-col items-center justify-center py-20 text-secondary bg-surface/10 rounded-xl border border-dashed border-white/10">
          <Briefcase className="h-12 w-12 text-secondary/50 mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">Session Not Started</h2>
          <p>You need to start a simulated or replay session to view active paper trades.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="glass-panel border-border/50">
          <CardHeader className="border-b border-border/20 pb-4">
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-gold" />
              Active Positions
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {positionsLoading ? (
              <div className="text-secondary">Loading positions...</div>
            ) : activePositions.length > 0 ? (
              <div className="space-y-4">
                {activePositions.map(pos => (
                  <div key={pos.position_id} className="bg-surface/30 border border-white/5 p-4 rounded-lg space-y-4">
                    <div className="flex justify-between items-center pb-4 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        <span className={`text-xl font-bold ${pos.side === 'LONG' ? 'text-bullish' : 'text-bearish'}`}>
                          {pos.side}
                        </span>
                        <span className="text-white font-mono text-lg">XAU/USD</span>
                      </div>
                      <div className="text-right">
                        <span className="block text-xs text-secondary mb-0.5">Unrealised PnL</span>
                        <span className={`font-mono text-lg font-semibold ${pos.unrealised_pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                          {pos.unrealised_pnl >= 0 ? '+' : ''}${pos.unrealised_pnl?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 text-sm pb-4 border-b border-white/5">
                      <div>
                        <span className="block text-secondary mb-1">Entry Price</span>
                        <span className="text-white font-mono font-semibold">${pos.entry_price?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-secondary mb-1">Position Size</span>
                        <span className="text-white font-mono">
                          {pos.lots} Lots {pos.initial_lots && pos.initial_lots !== pos.lots ? `(of ${pos.initial_lots})` : ''}
                        </span>
                      </div>
                      <div>
                        <span className="block text-secondary mb-1">Current Stop Loss</span>
                        <span className="text-white font-mono text-bearish font-semibold">
                          ${pos.stop_loss ? pos.stop_loss.toFixed(2) : '—'}
                        </span>
                      </div>
                      <div>
                        <span className="block text-secondary mb-1">Realised Leg PnL</span>
                        <span className={`font-mono font-semibold ${pos.realised_pnl > 0 ? 'text-bullish' : pos.realised_pnl < 0 ? 'text-bearish' : 'text-white'}`}>
                          {pos.realised_pnl > 0 ? '+' : ''}${pos.realised_pnl?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                    </div>

                    {pos.tp1 && (
                      <div className="space-y-2">
                        <span className="block text-xs font-semibold text-secondary uppercase tracking-wider">Partial Exits</span>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div className={`p-2 rounded border transition-all ${pos.tp1_hit ? 'bg-bullish-muted/10 border-bullish/30 text-bullish' : 'bg-surface/15 border-white/5 text-secondary'}`}>
                            <div className="font-semibold mb-0.5">TP1 (1/3)</div>
                            <div className="font-mono font-bold text-white">${pos.tp1.toFixed(2)}</div>
                            <div className="mt-1 font-semibold">{pos.tp1_hit ? '✓ HIT' : 'PENDING'}</div>
                          </div>
                          <div className={`p-2 rounded border transition-all ${pos.tp2_hit ? 'bg-bullish-muted/10 border-bullish/30 text-bullish' : 'bg-surface/15 border-white/5 text-secondary'}`}>
                            <div className="font-semibold mb-0.5">TP2 (1/3)</div>
                            <div className="font-mono font-bold text-white">${pos.tp2.toFixed(2)}</div>
                            <div className="mt-1 font-semibold">{pos.tp2_hit ? '✓ HIT' : 'PENDING'}</div>
                          </div>
                          <div className={`p-2 rounded border transition-all ${pos.tp3_hit ? 'bg-bullish-muted/10 border-bullish/30 text-bullish' : 'bg-surface/15 border-white/5 text-secondary'}`}>
                            <div className="font-semibold mb-0.5">TP3 (1/3)</div>
                            <div className="font-mono font-bold text-white">${pos.tp3.toFixed(2)}</div>
                            <div className="mt-1 font-semibold">{pos.tp3_hit ? '✓ HIT' : 'PENDING'}</div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-secondary bg-surface/10 rounded-xl border border-dashed border-white/10">
                <p>No active positions.</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="glass-panel border-border/50">
          <CardHeader className="border-b border-border/20 pb-4">
            <CardTitle className="flex items-center gap-2">
              <ArrowRightLeft className="h-5 w-5 text-neutral" />
              Pending Orders
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {pendingOrders.length > 0 ? (
              <div className="space-y-4">
                {pendingOrders.map(order => (
                  <div key={order.order_id} className="bg-surface/30 border border-white/5 p-4 rounded-lg space-y-4 relative group">
                    <button 
                      onClick={() => handleCancelOrder(order.order_id)}
                      className="absolute top-4 right-4 text-secondary hover:text-white transition-colors"
                      title="Cancel Order"
                    >
                      <X className="w-4 h-4" />
                    </button>
                    <div className="flex justify-between items-center pb-4 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        <span className={`text-lg font-bold ${order.side === 'LONG' ? 'text-bullish' : 'text-bearish'}`}>
                          {order.side} {order.type}
                        </span>
                        <span className="text-white font-mono">XAU/USD</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="block text-secondary mb-1">Requested Price</span>
                        <span className="text-white font-mono">${order.requested_price?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-secondary mb-1">Size</span>
                        <span className="text-white font-mono">{order.lots} Lots</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-secondary bg-surface/10 rounded-xl border border-dashed border-white/10">
                <p>No pending limit/stop orders.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      )}
    </div>
  );
}
