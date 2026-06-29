import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Shield } from 'lucide-react';
import { API_BASE_URL } from '../../config';


export function RiskMetricsCard() {
  const [metrics, setMetrics] = useState({
    balance: 10000.0,
    win_rate: 0.0,
    total_trades: 0,
    open_pnl: 0.0
  });

  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/metrics`);
        if (res.ok) {
          const data = await res.json();
          setMetrics(data);
          setError(false);
        } else {
          setError(true);
        }
      } catch (err) {
        console.error('Failed to fetch metrics:', err);
        setError(true);
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Card className="col-span-12 lg:col-span-4 border-border relative">
      {error && (
        <div className="absolute top-2 right-2 flex gap-2">
          <Badge variant="bearish">Network Error</Badge>
        </div>
      )}
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-secondary flex items-center gap-2">
          <Shield className="h-4 w-4 text-gold" />
          Daily Risk Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-secondary">Account Balance</span>
              <span className="text-white">${metrics.balance.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-secondary">Open PnL</span>
              <span className={metrics.open_pnl >= 0 ? 'text-bullish' : 'text-bearish'}>
                {metrics.open_pnl >= 0 ? '+' : ''}${metrics.open_pnl.toFixed(2)}
              </span>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-border/50">
            <div className="bg-surface/50 border border-border/50 rounded-lg p-3">
              <span className="block text-xs text-secondary mb-1">Win Rate</span>
              <span className="text-lg font-bold text-white">{(metrics.win_rate * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-surface/50 border border-border/50 rounded-lg p-3">
              <span className="block text-xs text-secondary mb-1">Total Trades</span>
              <span className="text-lg font-bold text-white">{metrics.total_trades}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
