import { Terminal } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { usePaginatedFetch } from '../../hooks/usePaginatedFetch';
import { API_BASE_URL } from '../../config';


export function LogsView() {
  const { data: logs, loading, loadingMore, hasMore, loadMore, error } = usePaginatedFetch(`${API_BASE_URL}/api/v1/logs`, 100);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">System Logs</h1>
        <p className="text-secondary">Real-time tail of scraper and backend events.</p>
      </div>

      <Card className="border-border">
        <CardHeader className="bg-surface/50 border-b border-border">
          <CardTitle className="text-sm flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            Backend Terminal
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="bg-black/50 p-4 h-[600px] overflow-y-auto font-mono text-xs rounded-b-xl">
            {error && <div className="text-bearish">Failed to connect to log stream: {error}</div>}
            {loading && logs.length === 0 && (
              <div className="text-secondary text-center py-4">Loading logs...</div>
            )}
            {!loading && logs?.length === 0 && (
              <div className="text-secondary text-center py-4">No system logs found.</div>
            )}
            
            {logs?.map((log) => (
              <div key={log.id} className="mb-2 flex gap-4 hover:bg-white/5 px-2 py-1 rounded">
                <span className="text-secondary shrink-0">
                  {new Date(log.timestamp).toISOString().split('T')[1].slice(0, -1)}
                </span>
                <span className={`shrink-0 font-bold w-16 ${
                  log.level === 'ERROR' ? 'text-bearish' : 
                  log.level === 'WARN' ? 'text-yellow-500' : 'text-blue-400'
                }`}>
                  [{log.level}]
                </span>
                <span className="text-neutral break-all">{log.message}</span>
              </div>
            ))}
            
            {hasMore && logs.length > 0 && (
              <div className="mt-4 flex justify-center pt-4 border-t border-border/50">
                <button 
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="px-4 py-2 bg-surface hover:bg-surface/80 text-secondary hover:text-white rounded text-sm transition-colors"
                >
                  {loadingMore ? 'Loading...' : 'Load Older Logs'}
                </button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
