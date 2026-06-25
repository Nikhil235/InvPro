import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { ShieldAlert, AlertTriangle } from 'lucide-react';
import { useFetch } from '../../hooks/useFetch';
import { API_BASE_URL } from '../../config';


export function RiskView() {
  const { data: settings } = useFetch(`${API_BASE_URL}/api/v1/settings`);
  const { data: metrics } = useFetch(`${API_BASE_URL}/api/v1/metrics`, 5000);

  const balance = metrics?.balance || 10000;
  const riskPct = settings?.risk_per_trade_pct || 0.01;
  const maxDrawdown = settings?.max_daily_drawdown || 300;
  const currentDrawdown = balance < 10000 ? 10000 - balance : 0;
  
  const drawdownPct = (currentDrawdown / maxDrawdown) * 100;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Risk Management</h1>
        <p className="text-secondary">Live monitoring of exposure and drawdown limits.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-gold" />
              Exposure Limits
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-secondary">Max Risk Per Trade</span>
                <span className="text-white font-mono">{(riskPct * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-secondary">Max Dollar Risk</span>
                <span className="text-bearish font-mono">${(balance * riskPct).toFixed(2)}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-bearish" />
              Daily Drawdown Limit
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
               <div className="flex justify-between text-sm mb-2">
                <span className="text-secondary">Current Drawdown</span>
                <span className="text-white font-mono">${currentDrawdown.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-secondary">Max Allowed</span>
                <span className="text-white font-mono">${maxDrawdown.toFixed(2)}</span>
              </div>
              
              <div className="mt-4">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-secondary">Limit Proximity</span>
                  <span className={`${drawdownPct > 80 ? 'text-bearish' : 'text-bullish'}`}>{drawdownPct.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-surface rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full ${drawdownPct > 80 ? 'bg-bearish' : 'bg-bullish'}`} 
                    style={{ width: `${Math.min(drawdownPct, 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
