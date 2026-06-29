import { createContext, useContext, useState, useEffect } from 'react';
import { toast } from 'sonner';
import { useLiveTradingData } from '../hooks/useLiveTradingData';
import { WS_URL, API_BASE_URL } from '../config';

const LiveDataContext = createContext(null);

export function LiveDataProvider({ children }) {
    const wsUrl = WS_URL;
    const [triggeredAlerts, setTriggeredAlerts] = useState([]);
    const [lastBrokerEvent, setLastBrokerEvent] = useState(null);
    const [activeSessionId, setActiveSessionId] = useState(null);
    const [sessionState, setSessionState] = useState('idle');
    const [accountData, setAccountData] = useState(null);

    useEffect(() => {
        // Fetch current session state on load (in case of page refresh)
        fetch(`${API_BASE_URL}/api/session/status`)
            .then(res => res.json())
            .then(data => {
                if (data.session_id) {
                    setActiveSessionId(data.session_id);
                    setSessionState(data.state);
                }
            })
            .catch(err => console.error("Failed to fetch session status", err));
    }, []);

    const liveData = useLiveTradingData(wsUrl, (message) => {
        const { event, data: payload } = message;

        if (event === 'TICK' || event === 'SIGNAL') {
            return;
        } 
        
        if (event === 'ACCOUNT_SNAPSHOT') {
            setAccountData(payload);
        }
        
        if (event === 'ORDER_REJECTED') {
            toast.warning(`Order Rejected: ${payload.reason}`, { duration: 5000 });
        } 
        
        if (event === 'ORDER_FILLED') {
            const side = payload.side?.value || payload.side;
            toast.success(`${side} Position Opened`, {
                description: `Filled ${payload.lots} lots at $${payload.fill_price?.toFixed(2)}`
            });
        } 
        
        if (event === 'TRADE_CLOSED') {
            const pnl = payload.net_pnl;
            const isWin = pnl >= 0;
            toast[isWin ? 'success' : 'error'](`Trade Closed`, {
                description: `P&L: ${isWin ? '+' : ''}$${pnl?.toFixed(2)}`
            });
        }
        
        if (event === 'SESSION_STATUS') {
            if (payload.session_id) {
                setActiveSessionId(payload.session_id);
            }
            if (payload.state) {
                setSessionState(payload.state);
            }
        }
        
        if (event === 'SYSTEM_ERROR') {
            toast.error(`SYSTEM ERROR: ${payload.message}`, { duration: Infinity });
            setActiveSessionId(null);
        }

        // Store the raw event so other components (like PaperTradesView) can react to it
        setLastBrokerEvent(message);
    });

    return (
        <LiveDataContext.Provider value={{ ...liveData, lastBrokerEvent, activeSessionId, sessionState, setSessionState, accountData }}>
            {children}
        </LiveDataContext.Provider>
    );
}

export function useLiveData() {
    return useContext(LiveDataContext);
}
