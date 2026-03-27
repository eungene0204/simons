"use client";

import { useRef, useEffect } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  UTCTimestamp,
  LineSeries,
} from "lightweight-charts";

export interface PerformancePoint {
  time: string;
  portfolio: number;
  benchmark: number;
}

interface Props {
  data: PerformancePoint[];
}

export default function PortfolioPerformanceChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const positiveRef = useRef<ISeriesApi<"Line"> | null>(null);
  const negativeRef = useRef<ISeriesApi<"Line"> | null>(null);
  const roRef = useRef<ResizeObserver | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;

    const init = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) { setTimeout(init, 100); return; }

      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#6b7280",
        },
        grid: {
          vertLines: { color: "#1e1e1e" },
          horzLines: { color: "#1e1e1e" },
        },
        width: w,
        height: h,
        timeScale: {
          borderColor: "#2a2a2a",
          tickMarkFormatter: (time: UTCTimestamp) => {
            const d = new Date(time * 1000);
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${m}-${day}`;
          },
        },
        rightPriceScale: {
          borderColor: "#2a2a2a",
          scaleMargins: { top: 0.08, bottom: 0.08 },
        },
        crosshair: {
          horzLine: { color: "#444", labelBackgroundColor: "#333" },
          vertLine: { color: "#444", labelBackgroundColor: "#333" },
        },
        handleScroll: true,
        handleScale: true,
      });

      chartRef.current = chart;

      const positive = chart.addSeries(LineSeries, {
        color: "#ef4444",
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => `${(v - 100).toFixed(1)}%` },
      });
      positiveRef.current = positive;

      const negative = chart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => `${(v - 100).toFixed(1)}%` },
      });
      negativeRef.current = negative;

      roRef.current = new ResizeObserver((entries) => {
        for (const e of entries) {
          const { width, height } = e.contentRect;
          if (width > 0 && height > 0 && chartRef.current) {
            chartRef.current.applyOptions({ width, height });
          }
        }
      });
      roRef.current.observe(container);
    };

    init();

    return () => {
      roRef.current?.disconnect();
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
      positiveRef.current = null;
      negativeRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!positiveRef.current || !negativeRef.current || data.length === 0) return;

    const toTs = (s: string): UTCTimestamp =>
      (new Date(s + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;

    const sorted = [...data].sort((a, b) => a.time.localeCompare(b.time));

    const positiveData = sorted.map((d) => ({
      time: toTs(d.time),
      value: d.benchmark >= 100 ? d.benchmark : undefined,
    })).filter((d) => d.value !== undefined);

    const negativeData = sorted.map((d) => ({
      time: toTs(d.time),
      value: d.benchmark < 100 ? d.benchmark : undefined,
    })).filter((d) => d.value !== undefined);

    positiveRef.current.setData(positiveData as any);
    negativeRef.current.setData(negativeData as any);

    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} className="w-full h-full" />;
}
