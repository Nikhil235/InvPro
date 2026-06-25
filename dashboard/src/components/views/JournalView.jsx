import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { usePaginatedFetch } from '../../hooks/usePaginatedFetch';
import { API_BASE_URL } from '../../config';


export function JournalView() {
  const { data: trades, loading, loadingMore, hasMore, loadMore, error } = usePaginatedFetch(`${API_BASE_URL}/api/v1/trades`, 50);

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Trade Journal</h1>
        <p className="text-secondary">Historical ledger of all executed paper trades.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Trade History</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <div className="text-bearish mb-4">Error loading trades: {error}</div>}
          
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-secondary uppercase bg-surface/30 border-b border-border/50">
                <tr>
                  <th className="px-4 py-3 font-medium rounded-tl-lg">Trade ID</th>
                  <th className="px-4 py-3 font-medium">Timestamp</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 font-medium text-right">Entry Price</th>
                  <th className="px-4 py-3 font-medium text-right">Size</th>
                  <th className="px-4 py-3 font-medium text-right rounded-tr-lg">PnL</th>
                </tr>
              </thead>
              <tbody>
                {loading && trades.length === 0 && (
                  <tr><td colSpan="6" className="text-center py-8 text-secondary">Loading trades...</td></tr>
                )}
                {trades?.length === 0 && !loading && (
                  <tr><td colSpan="6" className="text-center py-8 text-secondary">No historical trades found.</td></tr>
                )}
                {trades?.map((trade) => (
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
          
          {hasMore && trades.length > 0 && (
            <div className="mt-6 flex justify-center">
              <button 
                onClick={loadMore}
                disabled={loadingMore}
                className="px-4 py-2 bg-surface hover:bg-surface/80 text-white rounded text-sm transition-colors border border-border"
              >
                {loadingMore ? 'Loading...' : 'Load More Trades'}
              </button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
