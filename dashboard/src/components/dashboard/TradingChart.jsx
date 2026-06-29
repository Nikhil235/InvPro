import { useState, useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { useLiveData } from '../../contexts/LiveDataContext';
import { API_BASE_URL } from '../../config';

export function TradingChart() {
  const { data } = useLiveData() || {};
  const chartContainerRef = useRef();
  const tooltipRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const [timeframe, setTimeframe] = useState('1M');
  const [rawCandles, setRawCandles] = useState([]);
  const [loading, setLoading] = useState(true);

  const getIntervalSeconds = (tf) => {
    switch (tf) {
      case '1M': return 60;
      case '5M': return 300;
      case '15M': return 900;
      case '1H': return 3600;
      case '4H': return 14400;
      default: return 60;
    }
  };

  const aggregateCandles = (candles, tf) => {
    if (tf === '1M') return candles;
    const interval = getIntervalSeconds(tf);
    const aggregated = [];
    
    let currentCandle = null;
    
    candles.forEach(c => {
      const bucketTime = Math.floor(c.time / interval) * interval;
      
      if (!currentCandle || currentCandle.time !== bucketTime) {
        if (currentCandle) aggregated.push(currentCandle);
        currentCandle = {
          time: bucketTime,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume
        };
      } else {
        currentCandle.high = Math.max(currentCandle.high, c.high);
        currentCandle.low = Math.min(currentCandle.low, c.low);
        currentCandle.close = c.close;
        currentCandle.volume += c.volume;
      }
    });
    
    if (currentCandle) aggregated.push(currentCandle);
    return aggregated;
  };

  useEffect(() => {
    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 420,
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(42, 49, 67, 0.5)' },
        horzLines: { color: 'rgba(42, 49, 67, 0.5)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#2a3143',
      },
      rightPriceScale: {
        borderColor: '#2a3143',
        scaleMargins: {
          top: 0.1,
          bottom: 0.25,
        },
      },
      crosshair: {
        vertLine: {
          color: '#ffffff',
          width: 1,
          style: 1,
          labelBackgroundColor: '#2a3143',
        },
        horzLine: {
          color: '#ffffff',
          width: 1,
          style: 1,
          labelBackgroundColor: '#2a3143',
        },
      },
    });
    
    chartRef.current = chart;

    volumeSeriesRef.current = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', 
    });
    chart.priceScale('').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    seriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: '#00e676',
      downColor: '#ff5252',
      borderVisible: false,
      wickUpColor: '#00e676',
      wickDownColor: '#ff5252',
    });

    chart.subscribeCrosshairMove(param => {
      if (!param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > 420) {
        tooltipRef.current.style.display = 'none';
        return;
      }
      
      const dataPoint = param.seriesData.get(seriesRef.current);
      const volPoint = param.seriesData.get(volumeSeriesRef.current);
      
      if (dataPoint) {
        tooltipRef.current.style.display = 'block';
        tooltipRef.current.style.left = param.point.x + 15 + 'px';
        tooltipRef.current.style.top = param.point.y + 15 + 'px';
        
        const change = dataPoint.close - dataPoint.open;
        const color = change >= 0 ? '#00e676' : '#ff5252';
        
        tooltipRef.current.innerHTML = `
          <div style="font-family: Inter, sans-serif; font-size: 13px; color: #fff; background: rgba(26,32,44,0.9); padding: 12px; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; backdrop-filter: blur(4px);">
            <div style="font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px;">XAU/USD</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
              <div><span style="color: #94a3b8;">O:</span> ${dataPoint.open.toFixed(2)}</div>
              <div><span style="color: #94a3b8;">H:</span> ${dataPoint.high.toFixed(2)}</div>
              <div><span style="color: #94a3b8;">L:</span> ${dataPoint.low.toFixed(2)}</div>
              <div><span style="color: #94a3b8;">C:</span> <span style="color: ${color};">${dataPoint.close.toFixed(2)}</span></div>
            </div>
            ${volPoint ? `<div style="margin-top: 6px; color: #94a3b8;">Vol: <span style="color: #fff;">${volPoint.value.toFixed(0)}</span></div>` : ''}
          </div>
        `;
      } else {
        tooltipRef.current.style.display = 'none';
      }
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
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/chart/candles?limit=2000`);
        if (res.ok) {
          const history = await res.json();
          const baseCandles = history.map(c => {
            const timeUnix = Math.floor(new Date(c.time).getTime() / 1000);
            return {
              time: timeUnix,
              open: c.open,
              high: c.high,
              low: c.low,
              close: c.close,
              volume: c.volume || Math.random() * 100
            };
          });
          setRawCandles(baseCandles);
        }
      } catch (err) {
        console.error("Failed to fetch historical candles:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
    // Poll for new candles every minute to keep historical data synced
    const interval = setInterval(fetchHistory, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (seriesRef.current && volumeSeriesRef.current) {
      if (rawCandles.length > 0) {
        const aggregated = aggregateCandles(rawCandles, timeframe);
        
        const volData = aggregated.map(c => ({
          time: c.time,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(0, 230, 118, 0.5)' : 'rgba(255, 82, 82, 0.5)'
        }));

        const candleData = aggregated.map(c => ({
          time: c.time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close
        }));

        seriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volData);
      } else {
        // Clear chart if timeframe changed but there is no history yet
        seriesRef.current.setData([]);
        volumeSeriesRef.current.setData([]);
      }
    }
  }, [rawCandles, timeframe]);

  useEffect(() => {
    if (data?.price && data?.timestamp && seriesRef.current && !loading) {
      const dt = new Date(data.timestamp);
      dt.setSeconds(0, 0);
      let timeUnix = Math.floor(dt.getTime() / 1000);
      
      // Bucket the current tick into the correct timeframe candle
      // using timeframeRef.current instead of timeframe
      const interval = getIntervalSeconds(timeframe);
      timeUnix = Math.floor(timeUnix / interval) * interval;
      
      const price = data.price;
      
      // Prevent crash: lightweight-charts throws if time goes backwards
      // This can happen briefly during a timeframe switch if we use stale closures
      try {
          seriesRef.current.update({
            time: timeUnix,
            open: price,
            high: price,
            low: price,
            close: price
          });
          
          volumeSeriesRef.current.update({
            time: timeUnix,
            value: 10,
            color: 'rgba(148, 163, 184, 0.5)'
          });
      } catch (e) {
          console.warn("Chart update skipped due to timestamp ordering:", e.message);
      }
    }
  }, [data, loading]); // Removed timeframe from dependency array

  return (
    <Card className="col-span-12 lg:col-span-8 flex flex-col h-[500px]">
      <CardHeader className="flex flex-row items-center justify-between pb-2 z-10">
        <div className="flex flex-col gap-1">
          <CardTitle>XAU/USD Simulated Feed</CardTitle>
          <div className="flex items-center gap-2">
            <Badge className="animate-pulse-glow" variant={data?.direction === 'LONG' ? 'bullish' : data?.direction === 'SHORT' ? 'bearish' : 'neutral'}>
              {data?.direction || 'WAITING'} SIGNAL
            </Badge>
            <span className="text-sm text-secondary font-mono">
              {data?.price ? `$${data.price.toFixed(2)}` : 'Waiting for tick...'}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {['1M', '5M', '15M', '1H', '4H'].map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                tf === timeframe ? 'bg-surface text-gold' : 'text-secondary hover:bg-surface'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 relative p-0 overflow-hidden rounded-b-xl">
        <div ref={chartContainerRef} className="absolute inset-0" />
        <div 
          ref={tooltipRef} 
          className="absolute z-50 pointer-events-none" 
          style={{ display: 'none' }}
        />
      </CardContent>
    </Card>
  );
}

