import { useState, useEffect, useCallback } from 'react';

export function usePaginatedFetch(baseUrl, limit = 50) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);

  const fetchPage = useCallback(async (currentOffset, append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);

    try {
      const res = await fetch(`${baseUrl}?limit=${limit}&offset=${currentOffset}`);
      if (res.ok) {
        const newData = await res.json();
        
        if (newData.length < limit) {
          setHasMore(false);
        } else {
          setHasMore(true);
        }

        if (append) {
          setData(prev => [...prev, ...newData]);
        } else {
          setData(newData);
        }
      }
    } catch (err) {
      console.error(`Failed to fetch ${baseUrl}:`, err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [baseUrl, limit]);

  // Initial load
  useEffect(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (!loadingMore && hasMore) {
      const nextOffset = offset + limit;
      setOffset(nextOffset);
      fetchPage(nextOffset, true);
    }
  }, [loadingMore, hasMore, offset, limit, fetchPage]);

  const refresh = useCallback(() => {
    setOffset(0);
    fetchPage(0, false);
  }, [fetchPage]);

  return { data, loading, loadingMore, hasMore, loadMore, refresh };
}
