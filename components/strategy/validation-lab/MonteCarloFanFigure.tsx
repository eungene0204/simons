"use client";

import { useState, type MouseEvent } from "react";
import { t } from "@/lib/i18n";
import type { MonteCarloFan } from "@/components/strategy/backtest/monteCarloFan";
import LabFigure, { LegendSwatch } from "./LabFigure";
import { TRAIN_COLOR } from "./WalkForwardScheduleNode";

// 몬테카를로 경로 분포(팬 차트) — 체크포인트별 자산 배수의 5~95·25~75 백분위 띠, 중앙값, 원래 순서 경로,
// 옅은 개별 시나리오 몇 개. 세로축은 로그 눈금이라 같은 비율의 등락이 같은 높이로 보인다.

const WIDTH = 760;
const HEIGHT = 320;
const PAD = { left: 52, right: 16, top: 12, bottom: 30 };
const BAND_OUTER = "rgba(244, 241, 234, 0.08)";
const BAND_INNER = "rgba(244, 241, 234, 0.16)";
const MEDIAN = "#f4f1ea";

const NICE_MULTIPLES = [0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 7.5, 10, 15, 20, 30, 50, 75, 100];

/** 로그 범위 안의 보기 좋은 배수 눈금(최대 7개). */
export function fanYTicks(min: number, max: number): number[] {
  const inRange = NICE_MULTIPLES.filter((v) => v >= min && v <= max);
  if (!inRange.includes(1) && min <= 1 && max >= 1) inRange.push(1);
  inRange.sort((a, b) => a - b);
  if (inRange.length <= 7) return inRange;
  const stride = Math.ceil(inRange.length / 7);
  return inRange.filter((v, i) => v === 1 || i % stride === 0);
}

const fmtMultiple = (v: number) => `${v >= 10 ? v.toFixed(0) : v.toFixed(v < 1 ? 2 : 1)}×`;
const fmtChange = (v: number) => `${v >= 1 ? "+" : ""}${((v - 1) * 100).toFixed(1)}%`;

export default function MonteCarloFanFigure({ number, fan, iterations }: { number: string; fan: MonteCarloFan; iterations: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const last = fan.steps[fan.steps.length - 1] || 1;
  const all = [...fan.p05, ...fan.p95, ...fan.observed].filter((v) => v > 0 && Number.isFinite(v));
  const lo = Math.min(...all, 1) * 0.95;
  const hi = Math.max(...all, 1) * 1.05;
  const logLo = Math.log(lo);
  const logHi = Math.log(hi);
  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (step: number) => PAD.left + (step / last) * plotW;
  const y = (v: number) => PAD.top + (1 - (Math.log(Math.max(v, lo)) - logLo) / (logHi - logLo || 1)) * plotH;
  const line = (values: number[]) => values.map((v, i) => `${i === 0 ? "M" : "L"}${x(fan.steps[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const band = (upper: number[], lower: number[]) =>
    `${line(upper)}${lower
      .map((_, i) => {
        const j = lower.length - 1 - i;
        return `L${x(fan.steps[j]).toFixed(1)},${y(lower[j]).toFixed(1)}`;
      })
      .join("")}Z`;
  const ticks = fanYTicks(lo, hi);
  const unit = fan.stepUnit === "day" ? t("거래일") : t("거래");

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const step = ((px - PAD.left) / plotW) * last;
    let best = 0;
    for (let i = 1; i < fan.steps.length; i += 1) {
      if (Math.abs(fan.steps[i] - step) < Math.abs(fan.steps[best] - step)) best = i;
    }
    setHover(px < PAD.left || px > WIDTH - PAD.right ? null : best);
  };

  const h = hover;
  const tipX = h != null ? x(fan.steps[h]) : 0;
  const tipLeft = tipX > WIDTH * 0.62;

  return (
    <LabFigure
      number={number}
      title={t("자산 경로 분포")}
      testId="monte-carlo-fan-figure"
      legend={
        <>
          <LegendSwatch color={BAND_OUTER.replace("0.08", "0.3")} label={t("5~95% 범위")} />
          <LegendSwatch color={BAND_INNER.replace("0.16", "0.5")} label={t("25~75% 범위")} />
          <LegendSwatch color={MEDIAN} label={t("중앙값")} line />
          <LegendSwatch color={TRAIN_COLOR} label={t("원래 순서")} line dashed />
        </>
      }
      caption={t(
        "재표본한 시나리오 {0}개의 자산 배수(시작=1×)를 {1} 단위로 겹쳐 그린 분포입니다. 띠가 넓을수록 같은 수익률 표본으로도 결과가 크게 갈릴 수 있었다는 뜻입니다. 세로축은 로그 눈금입니다. 과거 데이터를 다시 섞은 시뮬레이션이며 미래 성과를 보장하지 않습니다.",
        iterations.toLocaleString(),
        unit,
      )}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="block h-auto w-full min-w-[560px]"
        role="img"
        aria-label={t("몬테카를로 시나리오 자산 경로 백분위 분포")}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(v)} y2={y(v)} stroke="#2a2926" strokeDasharray={v === 1 ? "4 3" : undefined} strokeWidth={v === 1 ? 1.2 : 1} />
            <text x={PAD.left - 6} y={y(v) + 3} fill="#a8a49a" fontSize={10} fontWeight={700} textAnchor="end">
              {fmtMultiple(v)}
            </text>
          </g>
        ))}
        {fan.samples.map((sample, i) => (
          <path key={i} d={line(sample)} fill="none" stroke="rgba(244, 241, 234, 0.12)" strokeWidth={0.8} />
        ))}
        <path d={band(fan.p95, fan.p05)} fill={BAND_OUTER} />
        <path d={band(fan.p75, fan.p25)} fill={BAND_INNER} />
        <path d={line(fan.p50)} fill="none" stroke={MEDIAN} strokeWidth={1.8} />
        <path d={line(fan.observed)} fill="none" stroke={TRAIN_COLOR} strokeWidth={1.6} strokeDasharray="5 3" />
        <text x={PAD.left} y={HEIGHT - 8} fill="#a8a49a" fontSize={10} fontWeight={700}>
          {fan.startDate ?? `0 ${unit}`}
        </text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 8} fill="#a8a49a" fontSize={10} fontWeight={700} textAnchor="end">
          {fan.endDate ?? `${last.toLocaleString()} ${unit}`}
        </text>
        {h != null && (
          <g pointerEvents="none">
            <line x1={tipX} x2={tipX} y1={PAD.top} y2={HEIGHT - PAD.bottom} stroke="#a8a49a" strokeWidth={1} />
            <g transform={`translate(${tipLeft ? tipX - 156 : tipX + 8}, ${PAD.top + 4})`}>
              <rect width={148} height={82} rx={6} fill="#1e1d1a" stroke="rgba(244, 241, 234, 0.2)" />
              <text x={8} y={15} fill="#a8a49a" fontSize={10} fontWeight={700}>
                {`${fan.steps[h].toLocaleString()} ${unit}`}
              </text>
              {[
                [t("95%"), fan.p95[h]],
                [t("중앙값"), fan.p50[h]],
                [t("5%"), fan.p05[h]],
                [t("원래 순서"), fan.observed[h]],
              ].map(([label, value], i) => (
                <g key={String(label)}>
                  <text x={8} y={31 + i * 14} fill="#a8a49a" fontSize={10} fontWeight={700}>
                    {label}
                  </text>
                  <text x={140} y={31 + i * 14} fill="#f4f1ea" fontSize={10} fontWeight={800} textAnchor="end">
                    {fmtChange(value as number)}
                  </text>
                </g>
              ))}
            </g>
          </g>
        )}
      </svg>
    </LabFigure>
  );
}
