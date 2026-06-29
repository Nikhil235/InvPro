import { useFetch } from '../../hooks/useFetch';
import { useLiveData } from '../../contexts/LiveDataContext';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { API_BASE_URL } from '../../config';


export function PerformanceView() {
  const { activeSessionId } = useLiveData() || {};
  const { data: metrics } = useFetch(`${API_BASE_URL}/api/v1/metrics`, 5000);
  const { data: trades } = useFetch(activeSessionId ? `${API_BASE_URL}/api/trades?session_id=${activeSessionId}` : null, 5000);

  // Generate an equity curve from historical trades
  const equityCurve = [];
  let runningBalance = 10000; // starting dummy balance

  if (trades && trades.length > 0) {
    // Trades come in descending order (newest first). Reverse for chart.
    const reversedTrades = [...trades].reverse();
    equityCurve.push({ index: 0, balance: runningBalance });
    
    reversedTrades.forEach((trade, i) => {
      if (trade.pnl !== null && trade.pnl !== undefined) {
        runningBalance += trade.pnl;
        equityCurve.push({ index: i + 1, balance: runningBalance });
      }
    });
  } else {
    equityCurve.push({ index: 0, balance: runningBalance });
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Performance Analytics</h1>
        <p className="text-secondary">Equity curve and historical trading statistics.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-border bg-surface/30">
          <CardContent className="p-6">
            <p className="text-sm text-secondary mb-1">Total Net Profit</p>
            <h2 className={`text-3xl font-bold ${metrics?.balance > 10000 ? 'text-bullish' : metrics?.balance < 10000 ? 'text-bearish' : 'text-white'}`}>
              {metrics?.balance > 10000 ? '+' : ''}${(metrics?.balance - 10000).toFixed(2) || '0.00'}
            </h2>
          </CardContent>
        </Card>
        <Card className="border-border bg-surface/30">
          <CardContent className="p-6">
            <p className="text-sm text-secondary mb-1">Win Rate</p>
            <h2 className="text-3xl font-bold text-white">
              {metrics?.win_rate !== undefined ? (metrics.win_rate * 100).toFixed(1) : '0.0'}%
            </h2>
          </CardContent>
        </Card>
        <Card className="border-border bg-surface/30">
          <CardContent className="p-6">
            <p className="text-sm text-secondary mb-1">Total Trades</p>
            <h2 className="text-3xl font-bold text-white">
              {metrics?.total_trades || 0}
            </h2>
          </CardContent>
        </Card>

        <Card className="col-span-full border-border">
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
          </CardHeader>
          <CardContent className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityCurve} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3143" vertical={false} />
                <XAxis dataKey="index" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis domain={['auto', 'auto']} stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} orientation="right" />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#151924', borderColor: '#2a3143', color: '#fff', borderRadius: '8px' }}
                  formatter={(value) => [`$${value.toFixed(2)}`, 'Balance']}
                  labelFormatter={() => ''}
                />
                <Line type="stepAfter" dataKey="balance" stroke="#fbbf24" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
