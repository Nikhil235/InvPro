import { useState } from 'react';
import { Play, RotateCcw, Square, Loader2 } from 'lucide-react';
import { useLiveData } from '../../contexts/LiveDataContext';
import { API_BASE_URL } from '../../config';
import { toast } from 'sonner';

export function SessionControl() {
  const { activeSessionId, sessionState, setSessionState } = useLiveData() || {};
  const [loading, setLoading] = useState(false);

  const startLive = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/session/live/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initial_capital: 10000.0 })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Started Simulated Session: ${data.session_id}`);
        if (setSessionState) setSessionState('running');
      } else {
        toast.error(`Error: ${data.detail || 'Failed to start'}`);
      }
    } catch (err) {
      toast.error('Failed to start simulated session');
    } finally {
      setLoading(false);
    }
  };

  const startReplay = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/session/replay/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initial_capital: 10000.0, speed: 1.0 })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Started Replay Session: ${data.session_id}`);
        if (setSessionState) setSessionState('running');
      } else {
        toast.error(`Error: ${data.detail || 'Failed to start'}`);
      }
    } catch (err) {
      toast.error('Failed to start replay session');
    } finally {
      setLoading(false);
    }
  };

  const stopSession = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/session/stop`, {
        method: 'POST'
      });
      if (res.ok) {
        toast.success('Session Stopped');
        if (setSessionState) setSessionState('completed');
      } else {
        toast.error('Failed to stop session');
      }
    } catch (err) {
      toast.error('Failed to stop session');
    } finally {
      setLoading(false);
    }
  };

  if (sessionState === 'running') {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-secondary font-mono mr-2">{activeSessionId}</span>
        <button
          onClick={stopSession}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20 rounded-md hover:bg-red-500/20 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5 fill-current" />}
          STOP
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={startLive}
        disabled={loading}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-500 border border-green-500/20 rounded-md hover:bg-green-500/20 transition-colors disabled:opacity-50"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
        SIMULATED
      </button>
      <button
        onClick={startReplay}
        disabled={loading}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-500 border border-blue-500/20 rounded-md hover:bg-blue-500/20 transition-colors disabled:opacity-50"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
        REPLAY
      </button>
    </div>
  );
}
