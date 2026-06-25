import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Settings, Save } from 'lucide-react';
import { useFetch } from '../../hooks/useFetch';
import { API_BASE_URL } from '../../config';


export function SettingsView() {
  const { data: initialSettings, loading } = useFetch(`${API_BASE_URL}/api/v1/settings`);
  const [settings, setSettings] = useState({
    risk_per_trade_pct: 0.01,
    max_daily_drawdown: 300.0,
    telegram_alerts: true,
    auto_trading: false
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  // Update local state when API fetch completes
  useEffect(() => {
    if (initialSettings) {
      setSettings(initialSettings);
    }
  }, [initialSettings]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : Number(value)
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        setMessage('Settings saved successfully!');
      } else {
        setMessage('Failed to save settings.');
      }
    } catch (err) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(''), 3000);
    }
  };

  if (loading) {
    return <div className="p-8 text-secondary">Loading configuration...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Strategy Configuration</h1>
        <p className="text-secondary">Update risk management and automation parameters.</p>
      </div>

      <Card className="border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-gold" />
            Risk Parameters
          </CardTitle>
          <CardDescription>Changes apply immediately to the next evaluation cycle.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-medium text-secondary">Risk Per Trade (%)</label>
              <input 
                type="number" 
                name="risk_per_trade_pct"
                step="0.001"
                value={settings.risk_per_trade_pct}
                onChange={handleChange}
                className="w-full bg-surface border border-border rounded-lg px-4 py-2 text-white focus:outline-none focus:border-gold"
              />
              <p className="text-xs text-neutral">Currently {(settings.risk_per_trade_pct * 100).toFixed(1)}% of account balance.</p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-secondary">Max Daily Drawdown ($)</label>
              <input 
                type="number" 
                name="max_daily_drawdown"
                value={settings.max_daily_drawdown}
                onChange={handleChange}
                className="w-full bg-surface border border-border rounded-lg px-4 py-2 text-white focus:outline-none focus:border-gold"
              />
              <p className="text-xs text-neutral">Trading pauses if this limit is breached.</p>
            </div>
          </div>

          <div className="border-t border-border/50 pt-6 space-y-4">
            <h3 className="text-lg font-medium text-white">System Toggles</h3>
            
            <div className="flex items-center justify-between p-4 bg-surface/30 rounded-lg border border-border">
              <div>
                <p className="text-white font-medium">Telegram Alerts</p>
                <p className="text-xs text-secondary">Send push notifications for new signals.</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" name="telegram_alerts" checked={settings.telegram_alerts} onChange={handleChange} className="sr-only peer" />
                <div className="w-11 h-6 bg-surface border border-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-secondary peer-checked:after:bg-gold after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:border-gold"></div>
              </label>
            </div>

            <div className="flex items-center justify-between p-4 bg-surface/30 rounded-lg border border-border">
              <div>
                <p className="text-white font-medium">Auto Trading</p>
                <p className="text-xs text-bearish">WARNING: Enables live execution to MT5/Paper Broker.</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" name="auto_trading" checked={settings.auto_trading} onChange={handleChange} className="sr-only peer" />
                <div className="w-11 h-6 bg-surface border border-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-secondary peer-checked:after:bg-bullish after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:border-bullish"></div>
              </label>
            </div>
          </div>

          <div className="border-t border-border/50 pt-6 flex items-center justify-between">
            <p className={`text-sm ${message.includes('Error') || message.includes('Failed') ? 'text-bearish' : 'text-bullish'}`}>
              {message}
            </p>
            <button 
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 bg-gold hover:bg-gold/90 text-background font-bold py-2 px-6 rounded-lg transition-colors disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
