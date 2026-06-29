import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { API_BASE_URL } from '../../config';
import { useLiveData } from '../../contexts/LiveDataContext';


export function TradeJournalTable() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const { activeSessionId } = useLiveData() || {};

  useEffect(() => {
    if (!activeSessionId) {
      setTrades([]);
      return;
    }

    let isMounted = true;
    
    const fetchTrades = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE_URL}/api/trades?session_id=${activeSessionId}`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted) setTrades(data);
        }
      } catch (err) {
        console.error('Failed to fetch trades:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchTrades();
    const interval = setInterval(fetchTrades, 5000);
    
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeSessionId]);

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  const formatPrice = (val) => {
    if (val === undefined || val === null || isNaN(Number(val)) || Number(val) <= 0) {
      return '—';
    }
    return `$${Number(val).toFixed(2)}`;
  };

  const formatPnl = (val) => {
    if (val === undefined || val === null || isNaN(Number(val))) {
      return '—';
    }
    const num = Number(val);
    return `${num > 0 ? '+' : ''}$${num.toFixed(2)}`;
  };

  return (
    <Card className="col-span-12">
      <CardHeader>
        <CardTitle className="text-lg">Recent Paper Trades</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-secondary uppercase bg-surface/30 border-b border-border/50">
              <tr>
                <th className="px-4 py-3 font-medium rounded-tl-lg">Trade ID</th>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium text-right">Entry Price</th>
                <th className="px-4 py-3 font-medium text-right">Close Price</th>
                <th className="px-4 py-3 font-medium text-right">Size</th>
                <th className="px-4 py-3 font-medium text-right">Net PnL</th>
              </tr>
            </thead>
            <tbody>
              {!activeSessionId && (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-yellow-500">
                    Start a session to view trades.
                  </td>
                </tr>
              )}
              {activeSessionId && trades.length === 0 && !loading && (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-secondary">
                    No recent trades found in this session.
                  </td>
                </tr>
              )}
              {trades.map((trade) => {
                const tradeId = trade.trade_id || trade.id;
                const entryPrice = trade.entry_price || trade.price;
                const closePrice = trade.exit_price !== undefined ? trade.exit_price : trade.close_price;
                const netPnl = trade.net_pnl !== undefined ? trade.net_pnl : trade.pnl;
                const size = trade.lots !== undefined ? trade.lots : trade.size;
                
                return (
                  <tr key={tradeId} className="border-b border-border/50 hover:bg-surface/20 transition-colors">
                    <td className="px-4 py-3 font-mono text-secondary">TRD-{tradeId || '—'}</td>
                    <td className="px-4 py-3 text-secondary">{formatTime(trade.close_time || trade.timestamp)}</td>
                    <td className="px-4 py-3">
                      <span className={(trade.side || trade.action) === 'LONG' || (trade.side || trade.action) === 'BUY' ? 'text-bullish font-medium' : 'text-bearish font-medium'}>
                        {trade.side || trade.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-right text-white">{formatPrice(entryPrice)}</td>
                    <td className="px-4 py-3 font-mono text-right text-white">{formatPrice(closePrice)}</td>
                    <td className="px-4 py-3 font-mono text-right text-secondary">{size !== undefined && size !== null ? size : '—'}</td>
                    <td className={`px-4 py-3 font-mono text-right font-medium ${netPnl > 0 ? 'text-bullish' : netPnl < 0 ? 'text-bearish' : 'text-secondary'}`}>
                      {formatPnl(netPnl)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
