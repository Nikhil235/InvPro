import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Briefcase } from 'lucide-react';
import { useLiveData } from '../../contexts/LiveDataContext';
import { useFetch } from '../../hooks/useFetch';
import { API_BASE_URL } from '../../config';


export function PositionCard() {
  const { data: liveData } = useLiveData() || {};
  const { data: metrics } = useFetch(`${API_BASE_URL}/api/v1/metrics`, 5000);
  const { data: trades } = useFetch(`${API_BASE_URL}/api/v1/trades`, 5000);

  const currentPrice = liveData?.price || 0;
  const lastTrade = trades && trades.length > 0 ? trades[0] : null;
  const hasOpenPosition = metrics?.open_pnl !== 0 || (lastTrade && (lastTrade.action === 'LONG' || lastTrade.action === 'SHORT'));
  return (
    <Card className="col-span-12 lg:col-span-4 border-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-secondary flex items-center gap-2">
          <Briefcase className="h-4 w-4" />
          Paper Position
        </CardTitle>
        {hasOpenPosition ? (
          <Badge variant={lastTrade?.action === 'SHORT' ? 'bearish' : 'bullish'}>OPEN {lastTrade?.action}</Badge>
        ) : (
          <Badge variant="neutral">FLAT</Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {hasOpenPosition ? (
          <>
            <div className="flex justify-between items-end">
              <div>
                <span className="block text-xs text-secondary mb-1">Unrealized PnL</span>
                <span className={`text-3xl font-bold ${metrics?.open_pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                  {metrics?.open_pnl >= 0 ? '+' : ''}${metrics?.open_pnl?.toFixed(2) || '0.00'}
                </span>
              </div>
              {lastTrade?.price && currentPrice ? (
                <span className={`text-sm font-medium px-2 py-1 rounded ${metrics?.open_pnl >= 0 ? 'text-bullish bg-bullish-muted/30' : 'text-bearish bg-bearish-muted/30'}`}>
                  {(((currentPrice - lastTrade.price) / lastTrade.price) * 100 * (lastTrade.action === 'SHORT' ? -1 : 1)).toFixed(3)}%
                </span>
              ) : null}
            </div>

            <div className="space-y-2 pt-4 border-t border-border">
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Entry Price</span>
                <span className="font-mono text-white">${lastTrade?.price?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Current Price</span>
                <span className="font-mono text-white">${currentPrice ? currentPrice.toFixed(2) : 'Waiting...'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Position Size</span>
                <span className="font-mono text-white">{lastTrade?.size || 0} Lots</span>
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-6">
            <p className="text-secondary mb-4">No active paper trades.</p>
            <div className="flex justify-between text-sm w-full pt-4 border-t border-border">
              <span className="text-secondary">Current Price</span>
              <span className="font-mono text-white">${currentPrice ? currentPrice.toFixed(2) : 'Waiting...'}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
