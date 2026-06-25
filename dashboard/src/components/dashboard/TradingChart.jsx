import { useState, useEffect, useRef } from 'react';
import { createChart, CandlestickSeries } from 'lightweight-charts';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { useLiveData } from '../../contexts/LiveDataContext';
import { API_BASE_URL } from '../../config';


export function TradingChart() {
  const { data } = useLiveData() || {};
  const chartContainerRef = useRef();
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Initialize chart
    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    chartRef.current = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 420, // Adjusted for CardContent padding
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#2a3143' },
        horzLines: { color: '#2a3143' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#2a3143',
      },
    });

    seriesRef.current = chartRef.current.addSeries(CandlestickSeries, {
      upColor: '#00e676',
      downColor: '#ff5252',
      borderVisible: false,
      wickUpColor: '#00e676',
      wickDownColor: '#ff5252',
    });

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    // Fetch historical candles
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/chart/candles?limit=500`);
        if (res.ok) {
          const history = await res.json();
          // Convert from backend format to lightweight-charts format
          // Backend returns ISO string in 'time'. We need unix timestamp.
          const formattedData = history.map(c => ({
            time: Math.floor(new Date(c.time).getTime() / 1000),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close
          }));
          
          if (seriesRef.current && formattedData.length > 0) {
            seriesRef.current.setData(formattedData);
          }
        }
      } catch (err) {
        console.error("Failed to fetch historical candles:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  useEffect(() => {
    // Append live ticks
    if (data?.price && data?.timestamp && seriesRef.current && !loading) {
      // Create a 1-minute candle tick
      const dt = new Date(data.timestamp);
      dt.setSeconds(0, 0);
      const timeUnix = Math.floor(dt.getTime() / 1000);
      
      seriesRef.current.update({
        time: timeUnix,
        open: data.price, // update() handles OHLC aggregation internally if the time matches the last candle!
        high: data.price,
        low: data.price,
        close: data.price
      });
    }
  }, [data, loading]);

  return (
    <Card className="col-span-12 lg:col-span-8 flex flex-col h-[500px]">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex flex-col gap-1">
          <CardTitle>XAU/USD Live Feed</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={data?.direction === 'LONG' ? 'bullish' : data?.direction === 'SHORT' ? 'bearish' : 'neutral'}>
              {data?.direction || 'WAITING'} SIGNAL
            </Badge>
            <span className="text-sm text-secondary">
              {data?.price ? `$${data.price.toFixed(2)}` : 'Waiting for tick...'}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {['1M', '5M', '15M', '1H', '4H'].map(tf => (
            <button
              key={tf}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                tf === '1M' ? 'bg-surface text-gold' : 'text-secondary hover:bg-surface'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 relative">
        <div ref={chartContainerRef} className="absolute inset-0" />
      </CardContent>
    </Card>
  );
}
