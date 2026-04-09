"use client";

import { useRef, useEffect, useMemo, useCallback } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  BusinessDay,
  ColorType,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
} from "lightweight-charts";

export interface OHLCV {
  time: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface CandlestickChartProps {
  data: OHLCV[];
}

type ChartPeriod = "day" | "week" | "month";

const calculateEMA = (data: number[], period: number): number[] => {
  if (data.length === 0) return [];

  const result: number[] = [];
  const multiplier = 2 / (period + 1);

  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      result.push(data[i]);
    } else {
      const ema = (data[i] - result[i - 1]) * multiplier + result[i - 1];
      result.push(ema);
    }
  }
  return result;
};

// Use BusinessDay for daily/weekly/monthly candles to avoid timezone drift.
const dateToBusinessDay = (dateStr: string): BusinessDay => {
  const [year, month, day] = dateStr.split("-").map(Number);
  return { year, month, day };
};

const formatBusinessDay = (time: BusinessDay | string): string => {
  if (typeof time === "string") return time;
  const year = String(time.year);
  const month = String(time.month).padStart(2, "0");
  const day = String(time.day).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export default function CandlestickChart({ data }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema5SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema60SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema120SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const hasAutoFittedRef = useRef(false);

  const chartPeriod: ChartPeriod = "day";

  // Filter and deduplicate data by time
  const deduplicatedData = useMemo(() => {
    if (!data || data.length === 0) return [];

    const timeMap = new Map<string, OHLCV>();

    const sortedData = [...data].sort((a, b) => {
      const timeA = new Date(a.time).getTime();
      const timeB = new Date(b.time).getTime();
      return timeA - timeB;
    });

    for (const item of sortedData) {
      const timeKey = item.time;
      if (!timeMap.has(timeKey)) {
        timeMap.set(timeKey, item);
      }
    }

    return Array.from(timeMap.values()).sort((a, b) => {
      const timeA = new Date(a.time).getTime();
      const timeB = new Date(b.time).getTime();
      return timeA - timeB;
    });
  }, [data]);

  // Aggregate data based on chart period
  const aggregatedData = useMemo(() => {
    if (chartPeriod === "day") {
      return deduplicatedData;
    }

    if (deduplicatedData.length === 0) return [];

    const aggregated: OHLCV[] = [];

    if (chartPeriod === "week") {
      let currentWeek: OHLCV[] = [];
      let currentWeekStart: Date | null = null;

      deduplicatedData.forEach((item, index) => {
        const itemDate = new Date(item.time);
        const weekStart = new Date(itemDate);
        weekStart.setDate(itemDate.getDate() - itemDate.getDay());

        if (
          !currentWeekStart ||
          weekStart.getTime() !== currentWeekStart.getTime()
        ) {
          if (currentWeek.length > 0) {
            const open = currentWeek[0].open;
            const close = currentWeek[currentWeek.length - 1].close;
            const high = Math.max(...currentWeek.map((d) => d.high));
            const low = Math.min(...currentWeek.map((d) => d.low));
            const volume = currentWeek.reduce((sum, d) => sum + d.volume, 0);

            aggregated.push({
              time: currentWeek[currentWeek.length - 1].time,
              open,
              high,
              low,
              close,
              volume,
            });
          }
          currentWeek = [item];
          currentWeekStart = weekStart;
        } else {
          currentWeek.push(item);
        }

        if (index === deduplicatedData.length - 1 && currentWeek.length > 0) {
          const open = currentWeek[0].open;
          const close = currentWeek[currentWeek.length - 1].close;
          const high = Math.max(...currentWeek.map((d) => d.high));
          const low = Math.min(...currentWeek.map((d) => d.low));
          const volume = currentWeek.reduce((sum, d) => sum + d.volume, 0);

          aggregated.push({
            time: currentWeek[currentWeek.length - 1].time,
            open,
            high,
            low,
            close,
            volume,
          });
        }
      });
    } else if (chartPeriod === "month") {
      let currentMonth: OHLCV[] = [];
      let currentMonthKey: string | null = null;

      deduplicatedData.forEach((item, index) => {
        const itemDate = new Date(item.time);
        const monthKey = `${itemDate.getFullYear()}-${itemDate.getMonth()}`;

        if (currentMonthKey !== monthKey) {
          if (currentMonth.length > 0) {
            const open = currentMonth[0].open;
            const close = currentMonth[currentMonth.length - 1].close;
            const high = Math.max(...currentMonth.map((d) => d.high));
            const low = Math.min(...currentMonth.map((d) => d.low));
            const volume = currentMonth.reduce((sum, d) => sum + d.volume, 0);

            aggregated.push({
              time: currentMonth[currentMonth.length - 1].time,
              open,
              high,
              low,
              close,
              volume,
            });
          }
          currentMonth = [item];
          currentMonthKey = monthKey;
        } else {
          currentMonth.push(item);
        }

        if (index === deduplicatedData.length - 1 && currentMonth.length > 0) {
          const open = currentMonth[0].open;
          const close = currentMonth[currentMonth.length - 1].close;
          const high = Math.max(...currentMonth.map((d) => d.high));
          const low = Math.min(...currentMonth.map((d) => d.low));
          const volume = currentMonth.reduce((sum, d) => sum + d.volume, 0);

          aggregated.push({
            time: currentMonth[currentMonth.length - 1].time,
            open,
            high,
            low,
            close,
            volume,
          });
        }
      });
    }

    return aggregated;
  }, [deduplicatedData, chartPeriod]);

  // Calculate EMA values
  const closePrices = useMemo(
    () => aggregatedData.map((d) => d.close),
    [aggregatedData]
  );
  const ema5 = useMemo(() => calculateEMA(closePrices, 5), [closePrices]);
  const ema20 = useMemo(() => calculateEMA(closePrices, 20), [closePrices]);
  const ema60 = useMemo(() => calculateEMA(closePrices, 60), [closePrices]);
  const ema120 = useMemo(() => calculateEMA(closePrices, 120), [closePrices]);

  // Prepare chart data
  const candlestickData = useMemo(() => {
    if (aggregatedData.length === 0) return [];
    return aggregatedData.map((item) => ({
      time: dateToBusinessDay(item.time),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
  }, [aggregatedData]);

  const volumeData = useMemo(() => {
    if (aggregatedData.length === 0) return [];
    return aggregatedData.map((item) => {
      const isUp = item.close >= item.open;
      return {
        time: dateToBusinessDay(item.time),
        value: item.volume,
        color: isUp ? "#ef4444" : "#3b82f6",
      };
    });
  }, [aggregatedData]);

  const ema5Data = useMemo(() => {
    if (aggregatedData.length === 0 || ema5.length === 0) return [];
    return aggregatedData.map((item, index) => ({
      time: dateToBusinessDay(item.time),
      value: ema5[index] || item.close,
    }));
  }, [aggregatedData, ema5]);

  const ema20Data = useMemo(() => {
    if (aggregatedData.length === 0 || ema20.length === 0) return [];
    return aggregatedData.map((item, index) => ({
      time: dateToBusinessDay(item.time),
      value: ema20[index] || item.close,
    }));
  }, [aggregatedData, ema20]);

  const ema60Data = useMemo(() => {
    if (aggregatedData.length === 0 || ema60.length === 0) return [];
    return aggregatedData.map((item, index) => ({
      time: dateToBusinessDay(item.time),
      value: ema60[index] || item.close,
    }));
  }, [aggregatedData, ema60]);

  const ema120Data = useMemo(() => {
    if (aggregatedData.length === 0 || ema120.length === 0) return [];
    return aggregatedData.map((item, index) => ({
      time: dateToBusinessDay(item.time),
      value: ema120[index] || item.close,
    }));
  }, [aggregatedData, ema120]);

  // Handle resize
  const handleResize = useCallback(() => {
    if (chartContainerRef.current && chartRef.current) {
      const width = chartContainerRef.current.clientWidth;
      const height = chartContainerRef.current.clientHeight;

      if (width > 0 && height > 0) {
        chartRef.current.applyOptions({
          width,
          height,
        });
      }
    }
  }, []);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Clean up existing chart
    if (chartRef.current) {
      try {
        chartRef.current.remove();
      } catch (e) {
        console.warn("Error removing chart:", e);
      }
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    // Wait for container to have dimensions
    const initChart = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;

      if (width === 0 || height === 0) {
        // Retry after a short delay
        setTimeout(initChart, 100);
        return;
      }

      try {
        const chart = createChart(container, {
          layout: {
            background: { type: ColorType.Solid, color: "#1a1a1a" },
            textColor: "#9ca3af",
          },
          localization: {
            locale: "ko-KR",
            dateFormat: "yyyy-MM-dd",
          },
          grid: {
            vertLines: { color: "#374151", style: 1 },
            horzLines: { color: "#374151", style: 1 },
          },
          width,
          height,
          timeScale: {
            timeVisible: false,
            secondsVisible: false,
            borderColor: "#4b5563",
            tickMarkFormatter: (time) => {
              if (typeof time === "object" && time !== null && "year" in time) {
                return formatBusinessDay(time as BusinessDay);
              }
              return String(time);
            },
          },
          rightPriceScale: {
            borderColor: "#4b5563",
            scaleMargins: {
              top: 0.1,
              bottom: 0.1,
            },
          },
        });

        // Verify chart was created successfully
        if (!chart || typeof chart.addSeries !== "function") {
          console.error("Chart creation failed or API mismatch");
          return;
        }

        chartRef.current = chart;

        // Create candlestick series
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
          upColor: "#ef4444",
          downColor: "#3b82f6",
          borderVisible: false,
          wickUpColor: "#ef4444",
          wickDownColor: "#3b82f6",
          priceFormat: {
            type: "price",
            precision: 0,
            minMove: 1,
          },
        });
        candlestickSeriesRef.current = candlestickSeries;

        // Create EMA lines
        const ema5Series = chart.addSeries(LineSeries, {
          color: "#f59e0b",
          lineWidth: 2,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: {
            type: "price",
            precision: 0,
            minMove: 1,
          },
        });
        ema5SeriesRef.current = ema5Series;

        const ema20Series = chart.addSeries(LineSeries, {
          color: "#22c55e",
          lineWidth: 2,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: {
            type: "price",
            precision: 0,
            minMove: 1,
          },
        });
        ema20SeriesRef.current = ema20Series;

        const ema60Series = chart.addSeries(LineSeries, {
          color: "#8b5cf6",
          lineWidth: 2,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: {
            type: "price",
            precision: 0,
            minMove: 1,
          },
        });
        ema60SeriesRef.current = ema60Series;

        const ema120Series = chart.addSeries(LineSeries, {
          color: "#ec4899",
          lineWidth: 2,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: {
            type: "price",
            precision: 0,
            minMove: 1,
          },
        });
        ema120SeriesRef.current = ema120Series;

        // Create volume series
        const volumeSeries = chart.addSeries(HistogramSeries, {
          color: "#26a69a",
          priceFormat: {
            type: "volume",
          },
          priceScaleId: "volume",
        });
        volumeSeriesRef.current = volumeSeries;

        // Create separate price scale for volume
        chart.priceScale("volume").applyOptions({
          scaleMargins: {
            top: 0.8,
            bottom: 0,
          },
        });

        // Set initial data
        if (candlestickData.length > 0) {
          candlestickSeries.setData(candlestickData);
        }
        if (ema5Data.length > 0) {
          ema5Series.setData(ema5Data);
        }
        if (ema20Data.length > 0) {
          ema20Series.setData(ema20Data);
        }
        if (ema60Data.length > 0) {
          ema60Series.setData(ema60Data);
        }
        if (ema120Data.length > 0) {
          ema120Series.setData(ema120Data);
        }
        if (volumeData.length > 0) {
          volumeSeries.setData(volumeData);
        }

        // Fit content
        if (candlestickData.length > 0) {
          chart.timeScale().fitContent();
          hasAutoFittedRef.current = true;
        }

        // Use ResizeObserver for better resize handling
        resizeObserverRef.current = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const { width, height } = entry.contentRect;
            if (width > 0 && height > 0 && chartRef.current) {
              chartRef.current.applyOptions({ width, height });
            }
          }
        });

        resizeObserverRef.current.observe(container);

        // Fallback to window resize
        window.addEventListener("resize", handleResize);
      } catch (error) {
        console.error("Error creating chart:", error);
      }
    };

    // Start initialization
    initChart();

    return () => {
      window.removeEventListener("resize", handleResize);
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      if (chartRef.current) {
        try {
          chartRef.current.remove();
        } catch (e) {
          console.warn("Error removing chart on cleanup:", e);
        }
        chartRef.current = null;
      }
      // Clear series refs
      candlestickSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ema5SeriesRef.current = null;
      ema20SeriesRef.current = null;
      ema60SeriesRef.current = null;
      ema120SeriesRef.current = null;
      hasAutoFittedRef.current = false;
    };
  }, []); // Only initialize once

  // Update data when it changes
  useEffect(() => {
    if (!chartRef.current) return;

    if (candlestickSeriesRef.current && candlestickData.length > 0) {
      candlestickSeriesRef.current.setData(candlestickData);
    }
    if (ema5SeriesRef.current && ema5Data.length > 0) {
      ema5SeriesRef.current.setData(ema5Data);
    }
    if (ema20SeriesRef.current && ema20Data.length > 0) {
      ema20SeriesRef.current.setData(ema20Data);
    }
    if (ema60SeriesRef.current && ema60Data.length > 0) {
      ema60SeriesRef.current.setData(ema60Data);
    }
    if (ema120SeriesRef.current && ema120Data.length > 0) {
      ema120SeriesRef.current.setData(ema120Data);
    }
    if (volumeSeriesRef.current && volumeData.length > 0) {
      volumeSeriesRef.current.setData(volumeData);
    }

    // Auto-fit only once on first data load. Realtime updates should not reset user zoom.
    if (candlestickData.length > 0 && chartRef.current && !hasAutoFittedRef.current) {
      chartRef.current.timeScale().fitContent();
      hasAutoFittedRef.current = true;
    }
  }, [candlestickData, ema5Data, ema20Data, ema60Data, ema120Data, volumeData]);

  return <div ref={chartContainerRef} className="h-full w-full" />;
}
