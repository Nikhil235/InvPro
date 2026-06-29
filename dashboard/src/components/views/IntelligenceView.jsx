import { useState, useEffect, useCallback } from 'react';
import { useLiveData } from '../../contexts/LiveDataContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Badge } from '../ui/badge';
import { toast } from 'sonner';
import { 
  Newspaper, BrainCircuit, Filter, Sparkles, Clock, 
  ChevronRight, ShieldAlert, Search, Plus, Send, RefreshCw,
  TrendingUp, Flame
} from 'lucide-react';
import { API_BASE_URL } from '../../config';

const isValidUrl = (urlString) => {
  if (!urlString || typeof urlString !== 'string') return false;
  try {
    const url = new URL(urlString);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
};

export function IntelligenceView() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [impact, setImpact] = useState('ALL');
  const [target, setTarget] = useState('ALL');
  const [hasMore, setHasMore] = useState(true);
  
  // Custom features state
  const [searchQuery, setSearchQuery] = useState('');
  const [showAnalyzer, setShowAnalyzer] = useState(false);
  const [manualHeadline, setManualHeadline] = useState('');
  const [manualSummary, setManualSummary] = useState('');
  const [manualUrl, setManualUrl] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [triggeringMock, setTriggeringMock] = useState(false);

  const { lastBrokerEvent } = useLiveData() || {};

  // Fetch events from the REST API
  const fetchEvents = useCallback(async (currentOffset, append = false) => {
    try {
      if (currentOffset === 0 && !append) setLoading(true);
      
      let url = `${API_BASE_URL}/api/news/events?limit=15&offset=${currentOffset}`;
      if (impact !== 'ALL') {
        url += `&impact=${impact}`;
      }
      if (target !== 'ALL') {
        url += `&target=${target}`;
      }

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (append) {
          setEvents(prev => {
            const existingIds = new Set(prev.map(e => e.id));
            const newFiltered = data.filter(e => !existingIds.has(e.id));
            return [...prev, ...newFiltered];
          });
        } else {
          setEvents(data);
        }
        setHasMore(data.length === 15);
      }
    } catch (err) {
      console.error("Failed to fetch news events:", err);
    } finally {
      setLoading(false);
    }
  }, [impact, target]);

  // Trigger fetch when filters change
  useEffect(() => {
    setOffset(0);
    fetchEvents(0, false);
  }, [fetchEvents]);

  // Trigger fetch when offset changes
  useEffect(() => {
    if (offset > 0) {
      fetchEvents(offset, true);
    }
  }, [offset, fetchEvents]);

  // WebSocket event listener
  useEffect(() => {
    if (lastBrokerEvent && lastBrokerEvent.event === 'NEWS_ALERT') {
      const newEvent = lastBrokerEvent.data;
      setEvents(prev => {
        if (prev.some(e => e.headline === newEvent.headline)) return prev;
        
        const isHighImpact = newEvent.impact_score === 'HIGH';
        toast(isHighImpact ? '🚨 High Impact News Alert' : '📊 News Event Logged', {
          description: newEvent.headline,
          duration: 6000,
          action: (isHighImpact && isValidUrl(newEvent.source_url)) ? {
            label: 'View',
            onClick: () => window.open(newEvent.source_url.includes('example.com') ? `https://www.google.com/search?q=${encodeURIComponent(newEvent.headline)}` : newEvent.source_url, '_blank', 'noopener,noreferrer')
          } : undefined
        });

        if (impact !== 'ALL' && newEvent.impact_score !== impact) return prev;
        if (target !== 'ALL' && !newEvent.target_market.toLowerCase().includes(target.toLowerCase())) return prev;
        return [newEvent, ...prev];
      });
    }
  }, [lastBrokerEvent, impact, target]);

  const loadMore = () => {
    if (!loading && hasMore) {
      setOffset(prev => prev + 15);
    }
  };

  const handleTriggerMock = async () => {
    setTriggeringMock(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/news/trigger_mock`, { method: 'POST' });
      if (res.ok) {
        toast.success("Simulated news event triggered and broadcasted!");
      } else {
        toast.error("Failed to trigger simulated news event.");
      }
    } catch (err) {
      console.error(err);
      toast.error("Network error triggering mock news.");
    } finally {
      setTriggeringMock(false);
    }
  };

  const handleAnalyzeSubmit = async (e) => {
    e.preventDefault();
    if (!manualHeadline.trim()) return;

    setAnalyzing(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/news/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ headline: manualHeadline, summary: manualSummary, url: manualUrl || null })
      });
      if (res.ok) {
        const data = await res.json();
        const cls = data.classification;
        toast.success(`Event Classified: ${cls.sentiment} | ${cls.impact_score} Impact`);
        setManualHeadline(''); setManualSummary(''); setManualUrl(''); setShowAnalyzer(false);
      } else {
        toast.error("Failed to classify event.");
      }
    } catch (err) {
      console.error(err);
      toast.error("Network error submitting event for analysis.");
    } finally {
      setAnalyzing(false);
    }
  };

  const getSentimentVariant = (sent) => {
    switch (sent) {
      case 'BULLISH': return 'bullish';
      case 'BEARISH': case 'RISK_OFF': return 'bearish';
      case 'VOLATILITY_SPIKE': return 'gold';
      default: return 'neutral';
    }
  };

  const getImpactColor = (score) => {
    switch (score) {
      case 'HIGH': return 'border-l-4 border-l-bearish';
      case 'MEDIUM': return 'border-l-4 border-l-neutral';
      default: return 'border-l-4 border-l-border';
    }
  };

  const formatTimestamp = (isoString) => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHrs = Math.floor(diffMins / 60);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHrs < 24) return `${diffHrs}h ago`;
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  };

  const filteredEvents = events.filter(event => {
    const text = `${event.headline} ${event.summary || ''} ${event.target_market || ''}`.toLowerCase();
    return text.includes(searchQuery.toLowerCase());
  });

  const stats = {
    total: filteredEvents.length,
    high: filteredEvents.filter(e => e.impact_score === 'HIGH').length,
    bullish: filteredEvents.filter(e => e.sentiment === 'BULLISH').length,
    bearish: filteredEvents.filter(e => e.sentiment === 'BEARISH' || e.sentiment === 'RISK_OFF').length,
    volatility: filteredEvents.filter(e => e.sentiment === 'VOLATILITY_SPIKE').length
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BrainCircuit className="h-6 w-6 text-gold animate-pulse-glow" />
            World Monitor Intelligence
          </h1>
          <p className="text-secondary mt-1">Real-time geopolitical news parsing and macroeconomic sentiment classification.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setShowAnalyzer(!showAnalyzer)} className="flex items-center gap-1.5 bg-surface hover:bg-surface/80 border border-border rounded px-3 py-1.5 text-xs text-white transition-colors">
            <Plus className="h-3.5 w-3.5 text-gold" />
            <span>Analyze Article</span>
          </button>
          <button onClick={handleTriggerMock} disabled={triggeringMock} className="flex items-center gap-1.5 bg-gold hover:bg-gold/90 text-background font-semibold rounded px-3 py-1.5 text-xs transition-colors disabled:opacity-50">
            <RefreshCw className={`h-3.5 w-3.5 ${triggeringMock ? 'animate-spin' : ''}`} />
            <span>Trigger Mock News</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="bg-surface/15 border-border/40 p-4 flex flex-col justify-between">
          <span className="text-xs text-secondary font-medium">Logged Alerts</span>
          <span className="text-2xl font-bold text-white mt-1">{stats.total}</span>
        </Card>
        <Card className="bg-surface/15 border-border/40 p-4 flex flex-col justify-between">
          <span className="text-xs text-secondary font-medium flex items-center gap-1">
            <ShieldAlert className="h-3.5 w-3.5 text-bearish" /> High Impact
          </span>
          <span className="text-2xl font-bold text-bearish mt-1">{stats.high}</span>
        </Card>
        <Card className="bg-surface/15 border-border/40 p-4 flex flex-col justify-between">
          <span className="text-xs text-secondary font-medium flex items-center gap-1">
            <TrendingUp className="h-3.5 w-3.5 text-bullish" /> Bullish
          </span>
          <span className="text-2xl font-bold text-bullish mt-1">{stats.bullish}</span>
        </Card>
        <Card className="bg-surface/15 border-border/40 p-4 flex flex-col justify-between">
          <span className="text-xs text-secondary font-medium flex items-center gap-1">
            <ShieldAlert className="h-3.5 w-3.5 text-bearish" /> Bearish
          </span>
          <span className="text-2xl font-bold text-bearish mt-1">{stats.bearish}</span>
        </Card>
        <Card className="bg-surface/15 border-border/40 p-4 flex flex-col justify-between col-span-2 md:col-span-1">
          <span className="text-xs text-secondary font-medium flex items-center gap-1">
            <Flame className="h-3.5 w-3.5 text-gold" /> Volatility
          </span>
          <span className="text-2xl font-bold text-gold mt-1">{stats.volatility}</span>
        </Card>
      </div>

      {showAnalyzer && (
        <Card className="bg-surface/40 border border-gold/30 shadow-lg animate-in fade-in slide-in-from-top-4 duration-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-white flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-gold" />
              Manual Article Analyzer
            </CardTitle>
            <CardDescription className="text-xs">Paste a custom macroeconomic headline to run the NLP classification.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleAnalyzeSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-secondary font-medium">Article Headline *</label>
                  <input type="text" required value={manualHeadline} onChange={e => setManualHeadline(e.target.value)} className="w-full bg-surface/80 border border-border rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-gold" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-secondary font-medium">Source URL (Optional)</label>
                  <input type="url" value={manualUrl} onChange={e => setManualUrl(e.target.value)} className="w-full bg-surface/80 border border-border rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-gold" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-secondary font-medium">Article Summary (Optional)</label>
                <textarea rows="2" value={manualSummary} onChange={e => setManualSummary(e.target.value)} className="w-full bg-surface/80 border border-border rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-gold resize-none" />
              </div>
              <div className="flex justify-end gap-2 pt-1.5">
                <button type="button" onClick={() => setShowAnalyzer(false)} className="bg-surface border border-border hover:bg-surface/80 text-xs font-semibold py-1.5 px-4 rounded text-white">Cancel</button>
                <button type="submit" disabled={analyzing} className="bg-gold hover:bg-gold/90 text-background font-bold text-xs py-1.5 px-4 rounded flex items-center gap-1.5 transition-colors disabled:opacity-50">
                  <Send className="h-3 w-3" />
                  {analyzing ? 'Analyzing...' : 'Analyze & Save'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface/20 border border-border/50 rounded-xl p-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-secondary/60" />
          <input type="text" placeholder="Search headlines, summaries or markets..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className="w-full bg-surface border border-border rounded-lg pl-9 pr-4 py-2 text-xs text-white focus:outline-none focus:border-gold" />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-surface/50 border border-border rounded px-3 py-1.5 text-xs text-secondary">
            <Filter className="h-3.5 w-3.5 text-gold" />
            <span>Filters</span>
          </div>
          <select value={impact} onChange={e => setImpact(e.target.value)} className="bg-surface border border-border rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-gold">
            <option value="ALL">All Impact Levels</option>
            <option value="HIGH">High Impact Only</option>
            <option value="MEDIUM">Medium Impact Only</option>
            <option value="LOW">Low Impact Only</option>
          </select>
          <select value={target} onChange={e => setTarget(e.target.value)} className="bg-surface border border-border rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-gold">
            <option value="ALL">All Target Assets</option>
            <option value="Gold">Gold / XAU</option>
            <option value="USD">USD / Fed</option>
            <option value="Oil">Oil / OPEC</option>
            <option value="INR">INR / India</option>
          </select>
        </div>
      </div>

      {loading && filteredEvents.length === 0 ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-32 rounded-xl bg-surface/20 border border-border/50 animate-pulse" />)}
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="text-center py-20 bg-surface/10 rounded-2xl border border-dashed border-border/80">
          <Newspaper className="h-12 w-12 text-secondary/40 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white">No intelligence events logged</h3>
          <p className="text-secondary mt-1 max-w-sm mx-auto">No news items matched your current filters or search query.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredEvents.map((event) => (
            <Card key={event.id || event.headline} className={`bg-surface/30 border border-border/50 hover:border-border transition-all duration-200 ${getImpactColor(event.impact_score)}`}>
              <CardContent className="p-5 flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="space-y-2 max-w-3xl">
                  <div className="flex items-start gap-2">
                    {event.impact_score === 'HIGH' && <ShieldAlert className="h-5 w-5 text-bearish shrink-0 mt-0.5" />}
                    <h3 className="font-semibold text-white leading-snug">
                      {isValidUrl(event.source_url) ? (
                        <a href={event.source_url.includes('example.com') ? `https://www.google.com/search?q=${encodeURIComponent(event.headline)}` : event.source_url} target="_blank" rel="noopener noreferrer" className="hover:text-gold transition-colors flex items-center gap-1 focus:outline-none focus:ring-1 focus:ring-gold focus:rounded">
                          {event.headline}
                          <ChevronRight className="h-4 w-4 inline text-secondary/40" />
                        </a>
                      ) : (
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span>{event.headline}</span>
                          <span className="text-[10px] bg-surface/50 border border-border/60 text-secondary/70 px-2 py-0.5 rounded select-none uppercase tracking-wider font-bold">Source unavailable</span>
                        </span>
                      )}
                    </h3>
                  </div>
                  {event.summary && <p className="text-sm text-secondary leading-relaxed font-normal">{event.summary}</p>}
                  <div className="flex flex-wrap gap-2 pt-1.5 items-center">
                    <Badge variant={getSentimentVariant(event.sentiment)}>{event.sentiment}</Badge>
                    <Badge variant="default" className="bg-surface/80">Target: {event.target_market}</Badge>
                    {event.confidence && (
                      <span className="text-xs text-secondary bg-surface/30 border border-border/30 px-2 py-0.5 rounded-full flex items-center gap-1 select-none">
                        <Sparkles className="h-3 w-3 text-gold" />
                        {Math.round(event.confidence * 100)}% Confidence
                      </span>
                    )}
                    {event.horizon_hours && (
                      <span className="text-xs text-secondary bg-surface/30 border border-border/30 px-2 py-0.5 rounded-full flex items-center gap-1 select-none">
                        <Clock className="h-3 w-3" />
                        {event.horizon_hours}h horizon
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right self-end md:self-start shrink-0">
                  <span className="text-xs text-secondary flex items-center gap-1 font-mono">
                    <Clock className="h-3.5 w-3.5 text-secondary/60" />
                    {formatTimestamp(event.timestamp)}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
          {hasMore && (
            <button onClick={loadMore} disabled={loading} className="w-full bg-surface/40 hover:bg-surface/80 border border-border text-xs text-white font-bold py-3 rounded-xl transition-all hover:scale-[1.005] duration-200 disabled:opacity-50">
              {loading ? 'Fetching Next Page...' : 'Load More Intelligence Events'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
