import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Briefcase, ArrowRightLeft } from 'lucide-react';
import { useFetch } from '../../hooks/useFetch';
import { useLiveData } from '../../contexts/LiveDataContext';
import { API_BASE_URL } from '../../config';

export function PaperTradesView() {
  // Fetch initial active positions from the new endpoint
  const { data: fetchedPositions, loading: positionsLoading } = useFetch(`${API_BASE_URL}/api/v1/positions`);
  const { data: fetchedOrders, loading: ordersLoading } = useFetch(`${API_BASE_URL}/api/v1/orders`);
  const { lastBrokerEvent } = useLiveData() || {};

  const [activePositions, setActivePositions] = useState([]);

  // Sync initial fetch
  useEffect(() => {
    if (fetchedPositions) {
      setActivePositions(fetchedPositions);
    }
  }, [fetchedPositions]);

  // Sync live broker events
  useEffect(() => {
    if (!lastBrokerEvent) return;

    if (lastBrokerEvent.type === 'ORDER_FILLED') {
      const pos = {
        position_id: lastBrokerEvent.payload.position_id,
        order_id: lastBrokerEvent.payload.order_id,
        side: lastBrokerEvent.payload.side.value || lastBrokerEvent.payload.side,
        entry_price: lastBrokerEvent.payload.fill_price,
        lots: lastBrokerEvent.payload.lots,
        unrealised_pnl: 0.0,
      };
      setActivePositions(prev => [pos, ...prev]);
    } else if (lastBrokerEvent.type === 'TRADE_CLOSED') {
      setActivePositions(prev => prev.filter(p => p.position_id !== lastBrokerEvent.payload.position_id));
    } else if (lastBrokerEvent.type === 'POSITION_UPDATE') {
      // Update P&L for all active positions
      setActivePositions(prev => {
        const updateMap = new Map();
        lastBrokerEvent.payload.positions?.forEach(p => {
          updateMap.set(p.position_id, p.unrealised_pnl);
        });
        
        return prev.map(pos => {
          if (updateMap.has(pos.position_id)) {
            return { ...pos, unrealised_pnl: updateMap.get(pos.position_id) };
          }
          return pos;
        });
      });
    }
  }, [lastBrokerEvent]);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Paper Trades</h1>
        <p className="text-secondary">Manage active positions and pending orders in the simulated broker environment.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-border">
          <CardHeader className="border-b border-border/50 pb-4">
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
                  <div key={pos.position_id} className="bg-surface/30 border border-border p-4 rounded-lg space-y-4">
                    <div className="flex justify-between items-center pb-4 border-b border-border/50">
                      <div className="flex items-center gap-3">
                        <span className={`text-xl font-bold ${pos.side === 'LONG' ? 'text-bullish' : 'text-bearish'}`}>
                          {pos.side}
                        </span>
                        <span className="text-white font-mono text-lg">XAU/USD</span>
                      </div>
                      <span className={`font-mono text-lg ${pos.unrealised_pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                        {pos.unrealised_pnl >= 0 ? '+' : ''}${pos.unrealised_pnl?.toFixed(2) || '0.00'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="block text-secondary mb-1">Entry Price</span>
                        <span className="text-white font-mono">${pos.entry_price?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-secondary mb-1">Size</span>
                        <span className="text-white font-mono">{pos.lots} Lots</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-secondary bg-surface/10 rounded-xl border border-dashed border-border">
                <p>No active positions.</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="flex items-center gap-2">
              <ArrowRightLeft className="h-5 w-5 text-neutral" />
              Pending Orders
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
             <div className="flex flex-col items-center justify-center py-12 text-secondary bg-surface/10 rounded-xl border border-dashed border-border">
                <p>No pending limit/stop orders.</p>
              </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

