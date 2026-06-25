import { createContext, useContext, useState } from 'react';
import { useLiveTradingData } from '../hooks/useLiveTradingData';
import { API_BASE_URL, WS_URL } from '../config';

const LiveDataContext = createContext(null);

export function LiveDataProvider({ children }) {
    const wsUrl = WS_URL;
    const restUrl = `${API_BASE_URL}/api/v1/signal/current`;
    const [triggeredAlerts, setTriggeredAlerts] = useState([]);
    const [lastBrokerEvent, setLastBrokerEvent] = useState(null);
    const liveData = useLiveTradingData(wsUrl, restUrl, (message) => {
        if (message.type === 'SIGNAL_UPDATE') {
            return;
        } else if (message.type === 'ALERT_TRIGGERED') {
            const alertId = Date.now();
            setTriggeredAlerts(prev => [...prev, { id: alertId, msg: message.payload.message }]);
            setTimeout(() => {
                setTriggeredAlerts(prev => prev.filter(a => a.id !== alertId));
            }, 5000);
        } else if (message.type === 'BROKER_EVENT') {
            setLastBrokerEvent(message.payload);
        }
    });

    return (
        <LiveDataContext.Provider value={{ ...liveData, lastBrokerEvent }}>
            {children}
            <div style={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
                {triggeredAlerts.map(alert => (
                    <div key={alert.id} style={{ background: 'red', color: 'white', padding: '10px', marginBottom: '10px', borderRadius: '4px' }}>
                        {alert.msg}
                    </div>
                ))}
            </div>
        </LiveDataContext.Provider>
    );
}

export function useLiveData() {
    return useContext(LiveDataContext);
}
