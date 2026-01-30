"use client";

import { useRef, useEffect, useMemo, useCallback } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  UTCTimestamp,
  LineSeries,
  AreaSeries,
  LineStyle,
} from "lightweight-charts";

export interface EquityDataPoint {
  time: string; // YYYY-MM-DD
  equity: number;
  buyHold?: number;
}

export interface DrawdownDataPoint {
  time: string; // YYYY-MM-DD
  drawdown: number;
}

interface BacktestChartProps {
  type: "equity" | "drawdown";
  equityData?: EquityDataPoint[];
  drawdownData?: DrawdownDataPoint[];
  height?: number;
}

// Convert YYYY-MM-DD to timestamp
const dateToTimestamp = (dateStr: string): UTCTimestamp => {
  const date = new Date(dateStr + "T00:00:00Z");
  return (date.getTime() / 1000) as UTCTimestamp;
};

// Format price to compact Korean format
const formatCompactPrice = (price: number): string => {
  if (price >= 100000000) {
    // 1억 이상
    return `${(price / 100000000).toFixed(1)}억`;
  } else if (price >= 10000) {
    // 1만 이상
    return `${(price / 10000).toFixed(0)}만`;
  } else if (price >= 1000) {
    // 1천 이상
    return `${(price / 1000).toFixed(1)}천`;
  }
  return price.toFixed(0);
};

export default function BacktestChart({
  type,
  equityData = [],
  drawdownData = [],
  height = 400,
}: BacktestChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const equitySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const buyHoldSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const drawdownSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // Prepare equity chart data
  const equityChartData = useMemo(() => {
    if (equityData.length === 0) return [];
    return equityData.map((item) => ({
      time: dateToTimestamp(item.time),
      value: item.equity,
    }));
  }, [equityData]);

  const buyHoldChartData = useMemo(() => {
    if (equityData.length === 0) return [];
    return equityData
      .filter((item) => item.buyHold !== undefined)
      .map((item) => ({
        time: dateToTimestamp(item.time),
        value: item.buyHold!,
      }));
  }, [equityData]);

  // Prepare drawdown chart data
  const drawdownChartData = useMemo(() => {
    if (drawdownData.length === 0) return [];
    return drawdownData.map((item) => ({
      time: dateToTimestamp(item.time),
      value: item.drawdown,
    }));
  }, [drawdownData]);

  // Handle resize
  const handleResize = useCallback(() => {
    if (chartContainerRef.current && chartRef.current) {
      const width = chartContainerRef.current.clientWidth;
      const chartHeight = chartContainerRef.current.clientHeight;

      if (width > 0 && chartHeight > 0) {
        chartRef.current.applyOptions({
          width,
          height: chartHeight,
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
      const chartHeight = container.clientHeight || height;

      if (width === 0 || chartHeight === 0) {
        // Retry after a short delay
        setTimeout(initChart, 100);
        return;
      }

      try {
        const chart = createChart(container, {
          layout: {
            background: { type: ColorType.Solid, color: "#0a0a0a" },
            textColor: "#666",
            fontSize: 10,
          },
          // @ts-ignore - Lightweight charts supports padding in layout
          padding: { top: 4, bottom: 4, left: 8, right: 40 }, 
          grid: {
            vertLines: { color: "#374151", style: 1, visible: true },
            horzLines: { color: "#374151", style: 1, visible: true },
          },
          width,
          height: chartHeight,
          timeScale: {
            timeVisible: true,
            secondsVisible: false,
            borderColor: "#4b5563",
          },
          rightPriceScale: {
            borderColor: "#4b5563",
            autoScale: true,
            scaleMargins: {
              top: 0.2,
              bottom: 0.2,
            },
            alignLabels: true,
          },
        });

        // Verify chart was created successfully
        if (!chart || typeof chart.addSeries !== "function") {
          console.error("Chart creation failed or API mismatch");
          return;
        }

        chartRef.current = chart;

        if (type === "equity") {
          // Create equity area series with custom price format
          const equitySeries = chart.addSeries(LineSeries, {
            color: "rgb(239, 68, 68)", // main-red
            lineWidth: 2,
            priceFormat: {
              type: "custom",
              formatter: (price: number) => formatCompactPrice(price),
              tickmarksFormatter: (priceValues: number[]) => {
                return priceValues.map((price) => formatCompactPrice(price));
              },
              minMove: 1,
            },
          });
          equitySeriesRef.current = equitySeries;

          // Create buy & hold line series if data exists
          if (buyHoldChartData.length > 0) {
            const buyHoldSeries = chart.addSeries(LineSeries, {
              color: "rgb(34, 197, 94)", // main-green
              lineWidth: 2,
              lineStyle: LineStyle.Solid,
              priceFormat: {
                type: "custom",
                formatter: (price: number) => formatCompactPrice(price),
                tickmarksFormatter: (priceValues: number[]) => {
                  return priceValues.map((price) => formatCompactPrice(price));
                },
                minMove: 1,
              },
            });
            buyHoldSeriesRef.current = buyHoldSeries;
            buyHoldSeries.setData(buyHoldChartData);
          }

          // Set equity data
          if (equityChartData.length > 0) {
            equitySeries.setData(equityChartData);
            chart.timeScale().fitContent();
          }
        } else if (type === "drawdown") {
          // Create drawdown area series
          // Note: Drawdown is in percentage, so we format it differently
          const drawdownSeries = chart.addSeries(LineSeries, {
            color: "rgb(239, 68, 68)", // main-red
            lineWidth: 2,
            priceFormat: {
              type: "price",
              precision: 2,
              minMove: 0.01,
            },
          });
          drawdownSeriesRef.current = drawdownSeries;

          // Set drawdown data
          if (drawdownChartData.length > 0) {
            drawdownSeries.setData(drawdownChartData);
            chart.timeScale().fitContent();
          }
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
      equitySeriesRef.current = null;
      buyHoldSeriesRef.current = null;
      drawdownSeriesRef.current = null;
    };
  }, [type, height, handleResize]); // Re-initialize when type changes

  // Update data when it changes
  useEffect(() => {
    if (!chartRef.current) return;

    if (type === "equity") {
      if (equitySeriesRef.current && equityChartData.length > 0) {
        equitySeriesRef.current.setData(equityChartData);
      }
      if (buyHoldSeriesRef.current && buyHoldChartData.length > 0) {
        buyHoldSeriesRef.current.setData(buyHoldChartData);
      }
      if (equityChartData.length > 0 && chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    } else if (type === "drawdown") {
      if (drawdownSeriesRef.current && drawdownChartData.length > 0) {
        drawdownSeriesRef.current.setData(drawdownChartData);
      }
      if (drawdownChartData.length > 0 && chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    }
  }, [type, equityChartData, buyHoldChartData, drawdownChartData]);

  return (
    <div className="w-full h-full relative group">
      {/* Legend Overlay */}
      <div className="absolute top-4 left-4 z-20 flex flex-col gap-1 b">
        <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
           <div className="w-2.5 h-2.5 rounded-full bg-main-red" />
           <span className="text-[10px] font-bold text-white">나의 전략</span>
        </div>
        <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
           <div className="w-2.5 h-2.5 rounded-full bg-main-green" />
           <span className="text-[10px] font-bold text-white">매수후보유</span>
        </div>
      </div>

      <div
        ref={chartContainerRef}
        className="w-full h-full"
      />
    </div>
  );
}
