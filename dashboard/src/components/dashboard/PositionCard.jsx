import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Briefcase } from 'lucide-react';
import { useLiveData } from '../../contexts/LiveDataContext';
import { useFetch } from '../../hooks/useFetch';
import { API_BASE_URL } from '../../config';


export function PositionCard() {
  const { activeSessionId, data: liveData } = useLiveData() || {};
  const { data: positions, error: positionsError } = useFetch(activeSessionId ? `${API_BASE_URL}/api/positions?session_id=${activeSessionId}` : null, 5000);
  const { data: ledger, error: ledgerError } = useFetch(activeSessionId ? `${API_BASE_URL}/api/ledger?session_id=${activeSessionId}` : null, 5000);

  const currentPrice = liveData?.price || 0;
  const position = positions && positions.length > 0 ? positions[0] : null;
  const hasOpenPosition = !!position;
  
  return (
    <Card className="col-span-12 lg:col-span-4 border-border relative">
      {(positionsError || ledgerError) && (
        <div className="absolute top-2 right-2 flex gap-2">
          <Badge variant="bearish">Network Error</Badge>
        </div>
      )}
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-secondary flex items-center gap-2">
          <Briefcase className="h-4 w-4" />
          Paper Position
        </CardTitle>
        {hasOpenPosition ? (
          <Badge variant={position.side === 'SHORT' ? 'bearish' : 'bullish'}>OPEN {position.side}</Badge>
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
                <span className={`text-3xl font-bold ${ledger?.unrealised_pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                  {ledger?.unrealised_pnl >= 0 ? '+' : ''}${ledger?.unrealised_pnl?.toFixed(2) || '0.00'}
                </span>
              </div>
              {position?.entry_price && currentPrice ? (
                <span className={`text-sm font-medium px-2 py-1 rounded ${ledger?.unrealised_pnl >= 0 ? 'text-bullish bg-bullish-muted/30' : 'text-bearish bg-bearish-muted/30'}`}>
                  {(((currentPrice - position.entry_price) / position.entry_price) * 100 * (position.side === 'SHORT' ? -1 : 1)).toFixed(3)}%
                </span>
              ) : null}
            </div>

            <div className="space-y-2 pt-4 border-t border-border">
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Entry Price</span>
                <span className="font-mono text-white">${position?.entry_price?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Current Price</span>
                <span className="font-mono text-white">${currentPrice ? currentPrice.toFixed(2) : 'Waiting...'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-secondary">Position Size</span>
                <span className="font-mono text-white">
                  {position?.lots || 0} Lots {position?.initial_lots && position?.initial_lots !== position?.lots ? `(of ${position?.initial_lots})` : ''}
                </span>
              </div>
              {position?.stop_loss && (
                <div className="flex justify-between text-sm">
                  <span className="text-secondary">Current SL</span>
                  <span className="font-mono text-bearish font-semibold">${position.stop_loss.toFixed(2)}</span>
                </div>
              )}
              {position?.realised_pnl !== undefined && position?.realised_pnl !== 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-secondary">Realised Leg PnL</span>
                  <span className={`font-mono font-semibold ${position.realised_pnl > 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {position.realised_pnl > 0 ? '+' : ''}${position.realised_pnl.toFixed(2)}
                  </span>
                </div>
              )}
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
