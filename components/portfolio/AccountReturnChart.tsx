"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  BaselineSeries,
  LineType,
  type Time,
} from "lightweight-charts";
import { getLocale, t } from "@/lib/i18n";
import type { ReturnPoint, ReturnRange } from "@/lib/virtual-account/returnSeries";

const RANGES: { value: ReturnRange; label: string }[] = [
  { value: "1m", label: "1개월" },
  { value: "3m", label: "3개월" },
  { value: "all", label: "전체" },
];

// 차트는 'YYYY-MM-DD' 를 BusinessDay 객체로 바꿔 넘긴다 — 문자열·유닉스 초가 와도 같은 날짜로 읽는다.
function toDate(time: Time): Date {
  if (typeof time === "number") return new Date(time * 1000);
  if (typeof time === "string") return new Date(`${time}T00:00:00Z`);
  return new Date(Date.UTC(time.year, time.month - 1, time.day));
}

/** 축 눈금: 10월 21일 / Oct 21 */
export function formatAxisDate(time: Time, locale: string = getLocale()): string {
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", timeZone: "UTC" }).format(toDate(time));
}

/** 십자선 라벨: 2026년 10월 21일 / Oct 21, 2026 */
export function formatCrosshairDate(time: Time, locale: string = getLocale()): string {
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }).format(toDate(time));
}

type LoadState = { range: ReturnRange; points: ReturnPoint[] } | "error" | null;

/** 계좌 전체(현금 + 보유 종목) 수익률의 일별 변화 — 기준은 총 납입액이다. */
export default function AccountReturnChart({ accountId }: { accountId: string }) {
  const [range, setRange] = useState<ReturnRange>("all");
  const [state, setState] = useState<LoadState>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Baseline"> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState(null);
    fetch(`/api/virtual-account/${accountId}/snapshots?range=${range}`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((body: { range: ReturnRange; points: ReturnPoint[] }) => {
        if (!cancelled) setState({ range: body.range, points: body.points });
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, range]);

  const points = state && state !== "error" ? state.points : null;
  // 점이 둘 이상이어야 선이 된다 — 오늘 개설한 계좌는 오늘 점 하나뿐이다.
  const hasLine = points != null && points.length >= 2;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !hasLine) return;

    let disposed = false;
    let ro: ResizeObserver | null = null;
    const init = () => {
      if (disposed) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) { setTimeout(init, 100); return; }

      const chart = createChart(container, {
        layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#6b7280" },
        grid: { vertLines: { color: "#1e1e1e" }, horzLines: { color: "#1e1e1e" } },
        width: w,
        height: h,
        localization: { timeFormatter: (time: Time) => formatCrosshairDate(time) },
        timeScale: { borderColor: "#2a2a2a", tickMarkFormatter: (time: Time) => formatAxisDate(time) },
        rightPriceScale: { borderColor: "#2a2a2a", scaleMargins: { top: 0.08, bottom: 0.08 } },
        crosshair: {
          horzLine: { color: "#444", labelBackgroundColor: "#333" },
          vertLine: { color: "#444", labelBackgroundColor: "#333" },
        },
      });
      chartRef.current = chart;
      seriesRef.current = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: 0 },
        topLineColor: "#ef4444",
        bottomLineColor: "#3b82f6",
        topFillColor1: "transparent",
        topFillColor2: "transparent",
        bottomFillColor1: "transparent",
        bottomFillColor2: "transparent",
        lineWidth: 2,
        lineType: LineType.Simple,
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => `${v.toFixed(2)}%` },
      });
      seriesRef.current.setData(
        (points ?? []).map((p) => ({ time: p.time, value: p.returnPct }))
      );
      chart.timeScale().fitContent();

      ro = new ResizeObserver((entries) => {
        for (const e of entries) {
          const { width, height } = e.contentRect;
          if (width > 0 && height > 0) chartRef.current?.applyOptions({ width, height });
        }
      });
      ro.observe(container);
    };
    init();

    return () => {
      disposed = true;
      ro?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [hasLine, points]);

  return (
    <div className="flex h-full w-full flex-col">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label={t("조회 기간")} className="inline-flex overflow-hidden rounded-md border border-white/[0.08]">
          {RANGES.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setRange(item.value)}
              aria-pressed={range === item.value}
              className={`px-3 py-1 text-xs font-bold transition-colors ${
                range === item.value ? "bg-white/[0.12] text-white" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {t(item.label)}
            </button>
          ))}
        </div>
        <div className="flex gap-x-4 text-xs font-bold text-gray-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 bg-[#ef4444]" aria-hidden="true" />
            {t("수익률")} ≥ 0%
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 bg-[#3b82f6]" aria-hidden="true" />
            {t("수익률")} &lt; 0%
          </span>
        </div>
      </div>
      <div className="relative min-h-0 w-full flex-1">
        {hasLine ? (
          <div ref={containerRef} className="h-full w-full" role="img" aria-label={t("일별 수익률")} />
        ) : (
          <p className="text-sm text-[var(--text-label)]">
            {state === null
              ? t("불러오는 중...")
              : state === "error"
                ? t("수익률 변화를 불러오지 못했습니다.")
                : t("아직 표시할 일별 기록이 없습니다. 장 마감 기준으로 하루에 한 점씩 채워집니다.")}
          </p>
        )}
      </div>
    </div>
  );
}
