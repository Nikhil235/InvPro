import { useState, useEffect } from 'react';

export function useFetch(url, pollIntervalMs = null) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    
    const fetchData = async () => {
      if (!url) {
        if (isMounted) setLoading(false);
        return;
      }
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(res.statusText);
        const json = await res.json();
        if (isMounted) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (isMounted) setError(err.message);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchData();

    let interval;
    if (pollIntervalMs) {
      interval = setInterval(fetchData, pollIntervalMs);
    }

    return () => {
      isMounted = false;
      if (interval) clearInterval(interval);
    };
  }, [url, pollIntervalMs]);

  return { data, loading, error };
}
