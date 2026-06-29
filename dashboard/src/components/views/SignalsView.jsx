import { useLiveData } from '../../contexts/LiveDataContext';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Activity, Zap } from 'lucide-react';

export function SignalsView() {
  const { data, isStale } = useLiveData() || {};

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Simulated Signals Breakdown</h1>
        <p className="text-secondary">Detailed view of all technical indicators feeding the strategy engine.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card className="col-span-full border-border bg-surface/30">
          <CardContent className="p-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`p-4 rounded-full ${data?.direction === 'LONG' ? 'bg-bullish/20 text-bullish' : data?.direction === 'SHORT' ? 'bg-bearish/20 text-bearish' : 'bg-neutral/20 text-neutral'}`}>
                <Activity className="h-8 w-8" />
              </div>
              <div>
                <p className="text-sm text-secondary">Current Consensus</p>
                <h2 className={`text-3xl font-bold ${data?.direction === 'LONG' ? 'text-bullish' : data?.direction === 'SHORT' ? 'text-bearish' : 'text-neutral'}`}>
                  {data?.direction || 'WAITING'}
                </h2>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-secondary">Last Update</p>
              <p className={`font-mono ${isStale ? 'text-orange-500' : 'text-white'}`}>
                {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '--:--:--'}
              </p>
            </div>
          </CardContent>
        </Card>

        {data?.signals && Object.entries(data.signals).length > 0 ? (
          Object.entries(data.signals).map(([indicator, value]) => (
            <Card key={indicator} className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-secondary flex items-center gap-2 uppercase tracking-wider">
                  <Zap className="h-4 w-4 text-gold" />
                  {indicator}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className={`text-2xl font-bold ${
                  value.includes('BUY') || value.includes('LONG') || value.includes('UP') ? 'text-bullish' : 
                  value.includes('SELL') || value.includes('SHORT') || value.includes('DOWN') ? 'text-bearish' : 
                  'text-neutral'
                }`}>
                  {value}
                </span>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="col-span-full text-center py-12 text-secondary bg-surface/10 rounded-xl border border-dashed border-border">
            No technical indicators currently available. Waiting for scraper cycle...
          </div>
        )}
      </div>
    </div>
  );
}
