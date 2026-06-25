import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { API_BASE_URL } from '../../config';


export function TradeJournalTable() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/trades`);
        if (res.ok) {
          const data = await res.json();
          setTrades(data);
        }
      } catch (err) {
        console.error('Failed to fetch trades:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();
    const interval = setInterval(fetchTrades, 5000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return ts;
    }
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
                <th className="px-4 py-3 font-medium text-right">Price</th>
                <th className="px-4 py-3 font-medium text-right">Size</th>
                <th className="px-4 py-3 font-medium text-right">PnL</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && !loading && (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-secondary">
                    No recent trades found.
                  </td>
                </tr>
              )}
              {trades.map((trade) => (
                <tr key={trade.id} className="border-b border-border/50 hover:bg-surface/20 transition-colors">
                  <td className="px-4 py-3 font-mono text-secondary">TRD-{trade.id}</td>
                  <td className="px-4 py-3 text-secondary">{formatTime(trade.timestamp)}</td>
                  <td className="px-4 py-3">
                    <span className={trade.action === 'LONG' || trade.action === 'BUY' ? 'text-bullish font-medium' : 'text-bearish font-medium'}>
                      {trade.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-right text-white">${Number(trade.price).toFixed(2)}</td>
                  <td className="px-4 py-3 font-mono text-right text-secondary">{trade.size}</td>
                  <td className={`px-4 py-3 font-mono text-right font-medium ${trade.pnl > 0 ? 'text-bullish' : trade.pnl < 0 ? 'text-bearish' : 'text-secondary'}`}>
                    {trade.pnl !== null ? `${trade.pnl > 0 ? '+' : ''}$${Number(trade.pnl).toFixed(2)}` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
