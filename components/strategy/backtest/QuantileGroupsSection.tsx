"use client";

import { useState } from "react";
import { ChartBar } from "phosphor-react";
import { QuantileGroupsResult } from "@/types/strategy";

interface Props {
  data: QuantileGroupsResult;
}

/** 수익/손실 의미색 — 플랫폼 공통(returnColor)과 동일 계열. */
const POSITIVE = "#ef4444"; // 수익(+)
const NEGATIVE = "#377af4"; // 손실(-)

function pct(v: number | undefined, decimals = 2) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;
}

function krw(v: number) {
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(1)}억`;
  if (Math.abs(v) >= 10_000) return `${(v / 10_000).toFixed(0)}만`;
  return v.toLocaleString();
}

function returnColorClass(v: number | undefined) {
  if (v == null) return "text-gray-400";
  if (v > 0) return "text-main-red";
  if (v < 0) return "text-main-blue";
  return "text-gray-400";
}

type Metric = "cagr" | "totalReturn" | "maxDrawdown";

const METRIC_OPTIONS: Array<{ key: Metric; label: string }> = [
  { key: "cagr", label: "CAGR" },
  { key: "totalReturn", label: "총 수익률" },
  { key: "maxDrawdown", label: "MDD" },
];

/**
 * 분위 그룹 비교(FR-BT-060) — 랭킹 순으로 종목 수가 동일한 G개 그룹을 각각 백테스트한
 * 결과를 막대 그래프 + 지표 테이블로 보여준다. 메인 결과는 1그룹 포트폴리오다.
 */
export default function QuantileGroupsSection({ data }: Props) {
  const [metric, setMetric] = useState<Metric>("cagr");
  const groups = data.groups ?? [];
  if (groups.length === 0) return null;

  // ── 막대 그래프 좌표 계산 (SVG viewBox 기준) ──
  const W = 720;
  const H = 240;
  const PAD_TOP = 28; // 값 라벨 공간
  const PAD_BOTTOM = 34; // 그룹 라벨 공간
  const PAD_X = 12;
  const plotH = H - PAD_TOP - PAD_BOTTOM;
  const values = groups.map((g) => g[metric] ?? 0);
  const maxV = Math.max(0, ...values);
  const minV = Math.min(0, ...values);
  const span = maxV - minV || 1;
  const yOf = (v: number) => PAD_TOP + ((maxV - v) / span) * plotH;
  const baselineY = yOf(0);
  const slot = (W - PAD_X * 2) / groups.length;
  const barW = Math.min(40, slot * 0.55);

  return (
    <div className="border-t border-white/[0.08] p-4" data-testid="quantile-groups-section">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <ChartBar className="w-4 h-4 text-gray-400" />
        <h4 className="text-base font-black uppercase tracking-widest text-white">
          분위 그룹 비교
        </h4>
        <span className="text-[10px] text-gray-500 font-bold ml-1">
          {data.orderLabel} · 종목 수 동일 {data.groupCount}개 그룹
          {data.groupCap ? ` · 그룹당 최대 ${data.groupCap}종목` : ""}
        </span>
        <div className="ml-auto flex items-center gap-1" role="group" aria-label="비교 지표 선택">
          {METRIC_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setMetric(opt.key)}
              className={`px-2 py-1 rounded-md text-[11px] font-bold transition-colors ${
                metric === opt.key
                  ? "bg-white/10 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-gray-600 mb-3">
        1그룹 = {data.metricLabel} 랭킹 최상위 구간(메인 결과), {data.groupCount}그룹 = 최하위
        구간. 그룹 비교는 순수 리밸런싱 기준의 과거 데이터 시뮬레이션 결과이며 미래 수익을
        보장하지 않습니다.
      </p>

      {/* 막대 그래프 — 그룹별 선택 지표 */}
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full min-w-[560px]"
          role="img"
          aria-label={`분위 그룹별 ${METRIC_OPTIONS.find((o) => o.key === metric)?.label} 막대 그래프`}
        >
          {/* 0% 기준선 */}
          <line
            x1={PAD_X}
            x2={W - PAD_X}
            y1={baselineY}
            y2={baselineY}
            stroke="rgba(255,255,255,0.15)"
            strokeWidth={1}
          />
          {groups.map((g, i) => {
            const v = g[metric] ?? 0;
            const x = PAD_X + slot * i + (slot - barW) / 2;
            const y0 = yOf(Math.max(v, 0));
            const h = Math.max(Math.abs(yOf(v) - baselineY), 1.5);
            const isMain = g.group === data.mainGroup;
            const fill = v >= 0 ? POSITIVE : NEGATIVE;
            return (
              <g key={g.group} data-testid={`quantile-bar-${g.group}`}>
                <title>{`${g.label}\n총 수익률 ${pct(g.totalReturn)} · CAGR ${pct(g.cagr)} · MDD ${pct(g.maxDrawdown)} · 샤프 ${g.sharpe.toFixed(2)} · 거래 ${g.trades}건`}</title>
                <rect
                  x={x}
                  y={y0}
                  width={barW}
                  height={h}
                  rx={3}
                  fill={fill}
                  opacity={isMain ? 1 : 0.75}
                  stroke={isMain ? "rgba(255,255,255,0.6)" : "none"}
                  strokeWidth={isMain ? 1.5 : 0}
                />
                {/* 값 라벨 — 텍스트 토큰(회색), 막대 위/아래 */}
                <text
                  x={x + barW / 2}
                  y={v >= 0 ? y0 - 6 : yOf(v) + 14}
                  textAnchor="middle"
                  fontSize={10}
                  fontFamily="monospace"
                  fill="#9ca3af"
                >
                  {`${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
                </text>
                {/* 그룹 라벨 */}
                <text
                  x={x + barW / 2}
                  y={H - PAD_BOTTOM + 16}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={isMain ? 800 : 500}
                  fill={isMain ? "#e0e0e0" : "#9ca3af"}
                >
                  {g.group}그룹
                </text>
                {isMain && (
                  <text
                    x={x + barW / 2}
                    y={H - PAD_BOTTOM + 29}
                    textAnchor="middle"
                    fontSize={9}
                    fill="#6b7280"
                  >
                    메인
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* 지표 테이블 */}
      <div className="overflow-x-auto mt-3">
        <table className="w-full text-left border-collapse" data-testid="quantile-groups-table">
          <thead>
            <tr className="bg-white/[0.06]">
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest rounded-l-lg">그룹</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">구간</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">총 수익률</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">CAGR</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">MDD</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">샤프</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">승률</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">거래</th>
              <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right rounded-r-lg">최종 자산</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const isMain = g.group === data.mainGroup;
              return (
                <tr
                  key={g.group}
                  className={`border-b border-white/[0.04] ${isMain ? "bg-white/[0.03]" : ""}`}
                >
                  <td className="py-2 px-3 text-xs font-bold text-gray-200 whitespace-nowrap">
                    {g.group}그룹
                    {isMain && (
                      <span className="ml-1.5 inline-flex items-center rounded bg-white/10 px-1.5 py-0.5 text-[9px] font-bold text-gray-300">
                        메인
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-500 text-right whitespace-nowrap">
                    {g.pctRange?.[0]}~{g.pctRange?.[1]}%
                  </td>
                  <td className={`py-2 px-3 text-xs font-bold font-mono tabular-nums text-right ${returnColorClass(g.totalReturn)}`}>
                    {pct(g.totalReturn)}
                  </td>
                  <td className={`py-2 px-3 text-xs font-bold font-mono tabular-nums text-right ${returnColorClass(g.cagr)}`}>
                    {pct(g.cagr)}
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-300 text-right">
                    {g.maxDrawdown.toFixed(2)}%
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-300 text-right">
                    {g.sharpe.toFixed(2)}
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-300 text-right">
                    {g.winRate.toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-300 text-right">
                    {g.trades}
                  </td>
                  <td className="py-2 px-3 text-xs font-mono tabular-nums text-gray-300 text-right whitespace-nowrap">
                    {krw(g.finalEquity)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
