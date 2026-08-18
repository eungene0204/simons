"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  HistogramSeries,
  createChart,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import { t } from "@/lib/i18n";
import {
  formatRebalanceChartValue,
  rebalanceChartMetricLabel,
  type RebalanceChartBar,
  type RebalanceChartMetric,
} from "./rebalanceComparison";

/** 수익/손실 의미색 — 월별 수익률 막대(BacktestChart monthly_returns)와 동일. */
const POSITIVE = "rgba(239, 68, 68, 0.8)";
const NEGATIVE = "rgba(55, 122, 244, 0.8)";
const TRANSPARENT = "rgba(0, 0, 0, 0)";

/**
 * 막대 i의 x축 자리 — lightweight-charts는 시간축뿐이라 하루 간격 가짜 시각을 쓰고 눈금은 주기 라벨로 바꿔 찍는다.
 * 히스토그램 막대는 자리 폭을 꽉 채우므로 막대마다 빈 자리(whitespace)를 끼워 간격을 만든다:
 * 막대 i는 자리 SLOTS_PER_BAR·i+1, 나머지 자리는 간격 → 막대 폭 = 자리 묶음의 1/SLOTS_PER_BAR.
 */
const BASE_TS = Date.UTC(2000, 0, 1) / 1000;
const DAY = 86_400;
/** 막대 하나가 차지하는 자리 수(막대 1 + 간격 2 = 막대 폭 1/3). */
export const SLOTS_PER_BAR = 3;
const slotTime = (slot: number) => (BASE_TS + slot * DAY) as UTCTimestamp;
const barSlot = (i: number) => SLOTS_PER_BAR * i + 1;
/** 시각 → 막대 인덱스(간격 자리·범위 밖이면 -1). */
function barIndexAt(time: unknown): number {
  const slot = Math.round(((time as number) - BASE_TS) / DAY);
  return slot % SLOTS_PER_BAR === 1 ? (slot - 1) / SLOTS_PER_BAR : -1;
}

interface Props {
  bars: RebalanceChartBar[];
  metric: RebalanceChartMetric;
  height?: number;
}

/**
 * 리밸런싱 주기별 선택 지표 막대 그래프(FR-BT-064) — TradingView lightweight-charts 히스토그램,
 * 월별 수익률 막대 차트(BacktestChart monthly_returns)와 같은 모습(색·격자·여백·범례·툴팁).
 * 주기 6개(+참고 행)를 x축 자리 하나씩에 놓고, 실패 주기·손익비 ∞는 막대 없이 라벨 자리만 둔다.
 * 현재 설정은 눈금 라벨 "(현재)"와 툴팁으로 표시한다.
 */
export default function RebalanceComparisonChart({ bars, metric, height = 220 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  // 차트 콜백(눈금·툴팁·축 포맷)은 생성 시 한 번 등록되므로 최신 값은 ref로 읽는다.
  const barsRef = useRef(bars);
  const metricRef = useRef(metric);
  barsRef.current = bars;
  metricRef.current = metric;

  // 차트 생성 — 컨테이너가 폭을 가진 뒤(ResizeObserver 첫 콜백)에 만든다.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const labelAt = (time: unknown): string => {
      const bar = barsRef.current[barIndexAt(time)];
      if (!bar) return "";
      return bar.isCurrent ? t("{0} (현재)", bar.label) : bar.label;
    };

    const ensureChart = (width: number) => {
      if (chartRef.current || width === 0) return;
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: "#151515" },
          textColor: "rgba(255,255,255,0.38)",
          fontSize: 10,
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.06)", style: 1, visible: true },
          horzLines: { color: "rgba(255,255,255,0.06)", style: 1, visible: true },
        },
        width,
        height,
        handleScroll: false,
        handleScale: false,
        timeScale: {
          borderColor: "rgba(255,255,255,0.10)",
          fixLeftEdge: true,
          fixRightEdge: true,
          // 간격 자리(whitespace)에는 눈금·크로스헤어를 두지 않는다 — 막대 자리에만 주기 라벨.
          ignoreWhitespaceIndices: true,
          // 라벨 폭 상한을 줄여 좁은 화면(모바일)에서도 6주기 라벨이 다 찍히게 한다.
          tickMarkMaxCharacterLength: 4,
          tickMarkFormatter: (time: unknown) => labelAt(time),
        },
        rightPriceScale: {
          borderColor: "rgba(255,255,255,0.10)",
          autoScale: true,
          scaleMargins: { top: 0.2, bottom: 0.2 },
          alignLabels: true,
        },
        localization: { timeFormatter: (time: unknown) => labelAt(time) },
      });
      chartRef.current = chart;

      const series = chart.addSeries(HistogramSeries, {
        priceFormat: {
          type: "custom",
          minMove: 0.01,
          formatter: (v: number) => formatRebalanceChartValue(metricRef.current, v),
        },
        priceScaleId: "right",
        base: 0,
        // 마지막 막대(연간)의 값 선·라벨은 비교표에서 의미가 없다.
        priceLineVisible: false,
        lastValueVisible: false,
      });
      seriesRef.current = series;
      applyData(series, chart, barsRef.current);

      const tooltip = tooltipRef.current;
      if (tooltip) {
        chart.subscribeCrosshairMove((param) => {
          const bar = param.time == null ? undefined : barsRef.current[barIndexAt(param.time)];
          if (
            !bar ||
            !param.point ||
            param.point.x < 0 ||
            param.point.x > container.clientWidth ||
            param.point.y < 0 ||
            param.point.y > container.clientHeight
          ) {
            tooltip.style.display = "none";
            return;
          }
          tooltip.style.display = "block";
          const v = bar.value;
          const colorClass = v == null ? "text-gray-300" : v >= 0 ? "text-main-red" : "text-main-blue";
          tooltip.innerHTML =
            `<div class="font-bold text-gray-400 mb-1 border-b border-gray-800 pb-1">${bar.label}${bar.isCurrent ? ` · ${t("현재 설정")}` : ""}</div>` +
            `<div class="text-white text-[10px] flex justify-between gap-4"><span>${rebalanceChartMetricLabel(metricRef.current)}:</span>` +
            `<span class="font-mono font-bold ${colorClass}">${bar.valueLabel}</span></div>`;
          // 위치 — BacktestChart와 같은 규칙(포인터 오른쪽 아래, 넘치면 반대쪽).
          const tooltipWidth = 140;
          const tooltipHeight = 60;
          const margin = 15;
          let left = param.point.x + margin;
          let top = param.point.y + margin;
          if (left + tooltipWidth > container.clientWidth) left = param.point.x - margin - tooltipWidth;
          if (top + tooltipHeight > container.clientHeight) top = param.point.y - margin - tooltipHeight;
          tooltip.style.left = `${left}px`;
          tooltip.style.top = `${top}px`;
        });
      }
    };

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? container.clientWidth;
      ensureChart(width);
      if (chartRef.current && width > 0) {
        chartRef.current.applyOptions({ width });
        chartRef.current.timeScale().fitContent();
      }
    });
    observer.observe(container);
    ensureChart(container.clientWidth);

    return () => {
      observer.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // height는 마운트 시 고정. bars/metric 변경은 아래 effect가 setData로 반영한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height]);

  // 데이터·지표 변경 → 시리즈 갱신
  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;
    applyData(series, chart, bars);
  }, [bars, metric]);

  return (
    <div className="group relative w-full" style={{ height: `${height}px` }} data-testid="rebalance-comparison-chart">
      {/* 범례 — 월별 수익률 차트와 같은 모양(좌상단 가로 배치) */}
      <div className="absolute top-4 left-4 z-20 flex flex-row flex-wrap items-center gap-1">
        <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
          <div className="flex gap-1">
            <div className="w-2.5 h-2.5 rounded-full bg-main-red" />
            <div className="w-2.5 h-2.5 rounded-full bg-main-blue" />
          </div>
          <span className="text-[10px] font-bold text-white" data-testid="rebalance-chart-metric">
            {t("주기별 {0}", rebalanceChartMetricLabel(metric))}
          </span>
        </div>
      </div>
      <div
        ref={tooltipRef}
        className="absolute z-30 pointer-events-none p-2 px-3 bg-[#0a0a0a]/90 border border-gray-800 rounded-lg shadow-2xl backdrop-blur-md hidden"
        style={{ minWidth: "120px" }}
      />
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

/**
 * 막대 → 히스토그램 데이터. 막대 자리 외의 자리는 간격(whitespace)으로 채운다
 * (총 SLOTS_PER_BAR·n 자리: 앞 간격 1, 막대, 뒤 간격 SLOTS_PER_BAR-2, …).
 * 마지막 자리만은 투명 0 막대(데이터)로 둔다 — 스크롤·확대를 끈 차트는 양끝을 고정하는데,
 * 오른쪽 끝을 마지막 *데이터* 자리에 맞추며 끝의 whitespace를 무시해 전체가 한 칸 왼쪽으로 밀린다
 * (헤드리스 Chrome 재현: 앞 여백 2칸·뒤 0칸 → 수정 후 1칸·1칸).
 */
export function toHistogramData(bars: RebalanceChartBar[]): Array<HistogramData<UTCTimestamp> | WhitespaceData<UTCTimestamp>> {
  const out: Array<HistogramData<UTCTimestamp> | WhitespaceData<UTCTimestamp>> = [];
  const total = bars.length * SLOTS_PER_BAR;
  for (let slot = 0; slot < total; slot++) {
    const i = barIndexAt(slotTime(slot));
    const bar = i >= 0 ? bars[i] : undefined;
    if (!bar) {
      out.push(slot === total - 1 ? { time: slotTime(slot), value: 0, color: TRANSPARENT } : { time: slotTime(slot) });
    } else if (bar.value == null) {
      // 값 없는 막대(실패·∞)는 투명한 0 높이 막대로 자리를 채운다 — whitespace로 두면 눈금 라벨·툴팁도 빠진다.
      out.push({ time: slotTime(slot), value: 0, color: TRANSPARENT });
    } else {
      out.push({ time: slotTime(slot), value: bar.value, color: bar.value >= 0 ? POSITIVE : NEGATIVE });
    }
  }
  return out;
}

function applyData(series: ISeriesApi<"Histogram">, chart: IChartApi, bars: RebalanceChartBar[]) {
  series.setData(toHistogramData(bars));
  chart.timeScale().fitContent();
}
