"use client";

import { useRef, useEffect } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  UTCTimestamp,
  BaselineSeries,
  LineType,
} from "lightweight-charts";
import { t } from "@/lib/i18n";

export interface PerformancePoint {
  time: string;
  /** 초기 자본을 100으로 둔 지수값 */
  portfolio: number;
}

interface Props {
  data: PerformancePoint[];
}

export default function PortfolioPerformanceChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Baseline"> | null>(null);
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
            const m = String(d.getUTCMonth() + 1).padStart(2, "0");
            const day = String(d.getUTCDate()).padStart(2, "0");
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

      const series = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: 100 },
        topLineColor: "#ef4444",
        bottomLineColor: "#3b82f6",
        topFillColor1: "transparent",
        topFillColor2: "transparent",
        bottomFillColor1: "transparent",
        bottomFillColor2: "transparent",
        lineWidth: 2,
        lineType: LineType.Curved,
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => `${(v - 100).toFixed(1)}%` },
      });
      seriesRef.current = series;

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
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;

    const toTs = (s: string): UTCTimestamp =>
      (new Date(s + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;

    const sorted = [...data].sort((a, b) => a.time.localeCompare(b.time));

    const seriesData = sorted.map((d) => ({
      time: toTs(d.time),
      value: d.portfolio,
    }));

    seriesRef.current.setData(seriesData);

    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div className="flex h-full w-full flex-col">
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-bold text-gray-400">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-[#ef4444]" aria-hidden="true" />
          {t("수익률")} ≥ 0%
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-[#3b82f6]" aria-hidden="true" />
          {t("수익률")} &lt; 0%
        </span>
      </div>
      <div ref={containerRef} className="min-h-0 w-full flex-1" role="img" aria-label={t("실현손익 추이")} />
    </div>
  );
}
