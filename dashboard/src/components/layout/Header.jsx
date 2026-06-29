import { Activity, ShieldAlert, Wifi, WifiOff, Loader2 } from 'lucide-react';
import { Badge } from '../ui/badge';
import { useLiveData } from '../../contexts/LiveDataContext';
import { SessionControl } from './SessionControl';

export function Header() {
  const { data, status, isStale, isMarketClosed } = useLiveData() || {};

  const getStatusDisplay = () => {
    if (status === 'connecting' || status === 'reconnecting') {
      return (
        <div className="flex items-center gap-2 text-xs text-yellow-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          {status === 'connecting' ? 'Connecting...' : 'Reconnecting...'}
        </div>
      );
    }
    if (isMarketClosed) {
      return (
        <div className="flex items-center gap-2 text-xs text-orange-500">
          <WifiOff className="h-4 w-4" />
          Market Closed
        </div>
      );
    }
    if (isStale) {
      return (
        <div className="flex items-center gap-2 text-xs text-orange-500">
          <WifiOff className="h-4 w-4" />
          Data Stale
        </div>
      );
    }
    return (
      <div className="flex items-center gap-2 text-xs text-bullish">
        <Wifi className="h-4 w-4" />
        Simulated Live
      </div>
    );
  };

  return (
    <header className="sticky top-0 z-50 flex h-16 w-full items-center justify-between border-b border-border bg-background/95 px-6 backdrop-blur">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Activity className="h-6 w-6 text-gold" />
          <span className="text-xl font-bold tracking-tight text-white">XAU<span className="text-gold">PRO</span></span>
        </div>
        <div className="h-6 w-px bg-border" />
        <div className="flex flex-col">
          <span className="text-sm font-bold text-white">XAU/USD</span>
          <span className="text-xs text-secondary">
            Simulated Price: {data?.price ? `$${data.price.toFixed(2)}` : 'Loading...'}
          </span>
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        <SessionControl />
        <div className="flex items-center gap-2 rounded-full border border-neutral/20 bg-neutral/10 px-3 py-1 text-xs font-medium text-neutral">
          <ShieldAlert className="h-4 w-4" />
          ADVISORY ONLY
        </div>
        <Badge variant="neutral">PAPER TRADING</Badge>
        {getStatusDisplay()}
      </div>
    </header>
  );
}
