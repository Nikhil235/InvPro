import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Bell, Plus, Trash2 } from 'lucide-react';
import { API_BASE_URL } from '../../config';


export function AlertsView() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ condition: 'price_above', value: '' });
  const [submitting, setSubmitting] = useState(false);

  const fetchAlerts = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/alerts`);
      if (res.ok) {
        const data = await res.json();
        setAlerts(data);
      }
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.value) return;
    
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          condition: form.condition,
          value: parseFloat(form.value),
          is_active: true
        })
      });
      if (res.ok) {
        setForm({ condition: 'price_above', value: '' });
        fetchAlerts();
      }
    } catch (err) {
      console.error("Failed to create alert", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/alerts/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchAlerts();
      }
    } catch (err) {
      console.error("Failed to delete alert", err);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Price Alerts</h1>
        <p className="text-secondary">Configure custom triggers that notify you when conditions are met.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5 text-gold" />
                New Alert
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Condition</label>
                  <select 
                    value={form.condition} 
                    onChange={e => setForm({...form, condition: e.target.value})}
                    className="w-full bg-surface border border-border rounded px-3 py-2 text-white focus:outline-none focus:border-gold"
                  >
                    <option value="price_above">Price goes ABOVE</option>
                    <option value="price_below">Price goes BELOW</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Price Level ($)</label>
                  <input 
                    type="number" 
                    step="0.01" 
                    required 
                    value={form.value} 
                    onChange={e => setForm({...form, value: e.target.value})}
                    className="w-full bg-surface border border-border rounded px-3 py-2 text-white focus:outline-none focus:border-gold"
                    placeholder="e.g. 2350.50"
                  />
                </div>
                <button 
                  type="submit" 
                  disabled={submitting}
                  className="w-full bg-gold hover:bg-gold-muted text-black font-bold py-2 px-4 rounded transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : 'Create Alert'}
                </button>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="md:col-span-2">
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-neutral" />
                Active Rules
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-secondary py-4">Loading rules...</div>
              ) : alerts.length === 0 ? (
                <div className="text-secondary py-8 text-center border border-dashed border-border rounded bg-surface/10">
                  No alerts configured.
                </div>
              ) : (
                <div className="space-y-3">
                  {alerts.map(alert => (
                    <div key={alert.id} className={`flex items-center justify-between p-3 rounded border ${alert.is_active ? 'bg-surface/50 border-border/50' : 'bg-surface/10 border-border/20 opacity-60'}`}>
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${alert.is_active ? 'bg-bullish' : 'bg-neutral'}`}></div>
                        <span className="text-secondary">
                          {alert.condition === 'price_above' ? 'Price >' : 'Price <'}
                        </span>
                        <span className="text-white font-mono font-bold">${alert.value.toFixed(2)}</span>
                        {!alert.is_active && <span className="text-xs text-bearish ml-2">(Triggered)</span>}
                      </div>
                      <button 
                        onClick={() => handleDelete(alert.id)}
                        className="text-secondary hover:text-bearish p-1 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
