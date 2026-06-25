import { useState, useEffect, useRef } from 'react';

export function useLiveTradingData(wsUrl, restUrl, onMessage) {
    const [data, setData] = useState(null);
    const [status, setStatus] = useState('connecting'); // connected, reconnecting, error
    const [isStale, setIsStale] = useState(false);
    const wsRef = useRef(null);
    const lastUpdateRef = useRef(Date.now());
    const reconnectTimeoutRef = useRef(null);

    // Initial fetch via REST to get current state immediately
    useEffect(() => {
        const fetchInitialState = async () => {
            try {
                const res = await fetch(restUrl);
                if (res.ok) {
                    const json = await res.json();
                    if (json.timestamp) {
                        setData(json);
                        lastUpdateRef.current = Date.now();
                        setIsStale(false);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch initial state:", err);
            }
        };
        fetchInitialState();
    }, [restUrl]);

    useEffect(() => {
        let isComponentMounted = true;
        let retryCount = 0;

        const connect = () => {
            if (!isComponentMounted) return;

            wsRef.current = new WebSocket(wsUrl);
            
            wsRef.current.onopen = () => {
                if (!isComponentMounted) return;
                setStatus('connected');
                retryCount = 0; // Reset backoff
            };
            
            wsRef.current.onmessage = (event) => {
                if (!isComponentMounted) return;
                try {
                    const message = JSON.parse(event.data);
                    if (onMessage) onMessage(message);
                    
                    if (message.type === 'SIGNAL_UPDATE') {
                        setData(message.payload);
                        lastUpdateRef.current = Date.now();
                        setIsStale(false);
                    }
                } catch (e) {
                    console.error("Failed to parse WS message", e);
                }
            };

            wsRef.current.onclose = () => {
                if (!isComponentMounted) return;
                setStatus('reconnecting');
                
                // Exponential backoff reconnect
                const timeout = Math.min(1000 * Math.pow(1.5, retryCount), 10000);
                retryCount++;
                
                reconnectTimeoutRef.current = setTimeout(connect, timeout);
            };

            wsRef.current.onerror = (err) => {
                console.error("WebSocket error", err);
                wsRef.current.close();
            };
        };

        connect();

        const staleCheckInterval = setInterval(() => {
            if (Date.now() - lastUpdateRef.current > 15000) {
                setIsStale(true);
            }
        }, 5000);

        return () => {
            isComponentMounted = false;
            if (wsRef.current) {
                wsRef.current.onclose = null; // Prevent reconnect logic on unmount
                wsRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            clearInterval(staleCheckInterval);
        };
    }, [wsUrl]);

    return { data, status, isStale };
}
