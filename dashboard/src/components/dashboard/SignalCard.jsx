import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { ArrowUpRight, TrendingUp, AlertTriangle, TrendingDown, Minus } from 'lucide-react';
import { useLiveData } from '../../contexts/LiveDataContext';

export function SignalCard() {
  const { data, status } = useLiveData() || {};

  const direction = data?.direction || 'FLAT';
  const price = data?.price || 0;
  
  const isLong = direction === 'LONG';
  const isShort = direction === 'SHORT';
  const isDisconnected = status === 'reconnecting' || status === 'error';
  
  let themeColor = 'text-neutral';
  let badgeVariant = 'neutral';
  let Icon = Minus;

  if (isDisconnected) {
    themeColor = 'text-bearish';
    badgeVariant = 'bearish';
    Icon = AlertTriangle;
  } else if (isLong) {
    themeColor = 'text-bullish';
    badgeVariant = 'bullish';
    Icon = TrendingUp;
  } else if (isShort) {
    themeColor = 'text-bearish';
    badgeVariant = 'bearish';
    Icon = TrendingDown;
  }

  const formatTime = (isoString) => {
    if (!isoString) return 'Waiting...';
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString();
    } catch {
      return 'Invalid Time';
    }
  };

  return (
    <Card className={`col-span-12 lg:col-span-4 bg-gradient-to-br from-card ${isDisconnected ? 'to-bearish-muted/10 border-bearish/20' : isLong ? 'to-bullish-muted/10 border-bullish/20' : isShort ? 'to-bearish-muted/10 border-bearish/20' : 'to-neutral-muted/10 border-neutral/20'}`}>
      <CardHeader>
        <CardTitle className="text-secondary flex items-center gap-2 text-sm">
          <Icon className={`h-4 w-4 ${themeColor}`} />
          Active Signal
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className={`text-4xl font-bold ${themeColor}`}>
              {isDisconnected ? 'OFFLINE' : direction}
            </span>
            <Badge variant={badgeVariant}>{isDisconnected ? 'DISCONNECTED' : 'SIMULATED'}</Badge>
          </div>
          <p className="text-secondary text-sm">
            {isDisconnected ? 'Waiting for connection...' : `Updated at ${formatTime(data?.timestamp)}`}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border/50">
          <div>
            <span className="block text-xs text-secondary mb-1">Entry Price</span>
            <span className="font-mono text-sm text-white">{price ? `$${price.toFixed(2)}` : 'N/A'}</span>
          </div>
          <div>
            <span className="block text-xs text-secondary mb-1">Rows Processed</span>
            <span className="font-mono text-sm text-white">{data?.row_count || 0}</span>
          </div>
        </div>

        <div className="bg-surface/50 rounded-lg p-3 flex items-start gap-3 mt-4 border border-border/50">
          <AlertTriangle className="h-4 w-4 text-neutral shrink-0 mt-0.5" />
          <p className="text-xs text-secondary leading-relaxed">
            Signals: {data?.signals ? Object.entries(data.signals).slice(0, 3).map(([k,v]) => `${k}=${v}`).join(', ') : 'Waiting for data...'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
