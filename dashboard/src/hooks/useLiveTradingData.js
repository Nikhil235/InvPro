import { useState, useEffect, useRef } from 'react';

export function useLiveTradingData(wsUrl, onMessage) {
    const [data, setData] = useState(null); // The latest tick data
    const [status, setStatus] = useState('connecting'); // connected, reconnecting, error
    const [isStale, setIsStale] = useState(false);
    const [isMarketClosed, setIsMarketClosed] = useState(false);
    const wsRef = useRef(null);
    const lastUpdateRef = useRef(Date.now());
    const reconnectTimeoutRef = useRef(null);

    useEffect(() => {
        let isComponentMounted = true;
        let retryCount = 0;

        const connect = () => {
            if (!isComponentMounted) return;

            wsRef.current = new WebSocket(wsUrl);
            
            wsRef.current.onopen = () => {
                if (!isComponentMounted) return;
                setStatus('connected');
                if (retryCount > 0) {
                    // Reconnected successfully
                    console.log("Reconnected successfully.");
                }
                retryCount = 0; // Reset backoff
            };
            
            wsRef.current.onmessage = (event) => {
                if (!isComponentMounted) return;
                try {
                    const message = JSON.parse(event.data);
                    
                    // message format from backend: {"event": "...", "data": {...}}
                    if (onMessage) onMessage(message);
                    
                    if (message.event === 'TICK' || message.event === 'SIGNAL') {
                        setData(message.data);
                        lastUpdateRef.current = Date.now();
                        setIsStale(false);
                    }
                    
                    if (message.event === 'SESSION_STATUS') {
                        if (message.data.state === 'stale') {
                            setIsStale(true);
                            setIsMarketClosed(false);
                        } else if (message.data.state === 'market_closed') {
                            setIsStale(false);
                            setIsMarketClosed(true);
                        } else if (message.data.state === 'running') {
                            setIsStale(false);
                            setIsMarketClosed(false);
                            lastUpdateRef.current = Date.now();
                        }
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
            // Considered stale if no tick received for 15 seconds
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

    return { data, status, isStale, isMarketClosed };
}
