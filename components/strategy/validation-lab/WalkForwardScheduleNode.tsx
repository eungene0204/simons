"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Columns } from "phosphor-react";
import { t } from "@/lib/i18n";
import { EXPERIMENT_NODE_W, SCHEDULE_NODE_W, type ScheduleNode } from "./experimentGraph";

// 워크포워드 창 배치 노드 — 캔버스 안에서 창 분할 단계 밑에 붙어, 창마다 한 줄씩 학습(파랑)·검증(주황) 막대를
// 같은 시간축에 쌓는다. 결과가 있으면 줄 끝에 그 창의 학습·검증 CAGR을 적는다. 색은 설정 화면의 학습·검증 눈금과 같다.

export const TRAIN_COLOR = "#62A8CB";
export const VALIDATION_COLOR = "#FF9933";

const PAD_X = 12;
const WIDTH = SCHEDULE_NODE_W - PAD_X * 2;
const LABEL_W = 36;
const VALUE_W = 132;
const ROW_H = 22;
const BAR_H = 10;
const AXIS_H = 24;

function yearTicks(dates: string[], totalBars: number): Array<{ index: number; label: string }> {
  if (dates.length < 2) {
    return [0, Math.round(totalBars / 2), totalBars].map((index) => ({ index, label: String(index) }));
  }
  const ticks: Array<{ index: number; label: string }> = [];
  let lastYear = "";
  dates.forEach((date, index) => {
    const year = date.slice(0, 4);
    if (year !== lastYear) {
      ticks.push({ index, label: year });
      lastYear = year;
    }
  });
  // 연도 눈금이 너무 많으면 고르게 덜어 낸다.
  const stride = Math.ceil(ticks.length / 10);
  return ticks.filter((_, i) => i % stride === 0);
}

const fmtCagr = (v: number | null) => (v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(1)}%`);

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-[10px] font-bold text-[var(--text-label)]">
      <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

const WalkForwardScheduleNode = memo(function WalkForwardScheduleNode({ data, selected }: NodeProps<ScheduleNode>) {
  const { spans, totalBars, dates, anchor, trainBars, validationBars, outcomes } = data;
  const hasOutcomes = !!outcomes && outcomes.length > 0;
  const plotW = WIDTH - LABEL_W - (hasOutcomes ? VALUE_W : 0);
  const x = (index: number) => LABEL_W + (Math.min(Math.max(index, 0), totalBars) / Math.max(totalBars, 1)) * plotW;
  const plotH = spans.length * ROW_H;
  const height = plotH + AXIS_H;
  const byWindow = new Map((outcomes ?? []).map((o) => [o.window, o]));
  const ticks = yearTicks(dates, totalBars);

  return (
    <div
      className={`cursor-pointer rounded-2xl border bg-[var(--lab-node)] ${selected ? "border-[var(--lab-border-focus)]" : "border-[var(--lab-border-strong)]"}`}
      style={{ width: SCHEDULE_NODE_W }}
      data-testid="walk-forward-schedule-node"
    >
      {/* 창 분할 노드 바로 밑에서 들어오도록 연결점을 그 노드 가운데에 맞춘다. */}
      <Handle
        type="target"
        id="in"
        position={Position.Top}
        style={{ left: EXPERIMENT_NODE_W / 2 }}
        className="!h-2 !w-2 !rounded-full !border !border-[var(--lab-border-strong)] !bg-[var(--lab-panel)]"
        isConnectable={false}
      />
      <div className="flex items-center gap-2.5 border-b border-[var(--lab-border)] px-3 py-2">
        <Columns size={15} weight="duotone" className="flex-shrink-0 text-white" />
        <span className="text-xs font-black text-white">{t("워크포워드 창 배치")}</span>
        <span className="ml-auto flex items-center gap-3">
          <Swatch color={TRAIN_COLOR} label={t("학습(IS) — 파라미터 탐색")} />
          <Swatch color={VALIDATION_COLOR} label={t("검증(OOS) — 고른 값 적용")} />
        </span>
      </div>
      <div className="px-3 pt-3">
        {spans.length === 0 ? (
          <p className="py-5 text-center text-[11px] font-bold text-[var(--text-label)]">{t("현재 설정으로는 만들 수 있는 창이 없습니다.")}</p>
        ) : (
          <svg width={WIDTH} height={height} viewBox={`0 0 ${WIDTH} ${height}`} className="block" role="img" aria-label={t("워크포워드 창 {0}개의 학습·검증 구간 배치", spans.length)}>
            {ticks.map((tick) => (
              <g key={`${tick.index}-${tick.label}`}>
                <line x1={x(tick.index)} x2={x(tick.index)} y1={0} y2={plotH} stroke="var(--lab-border)" strokeWidth={1} />
                <text x={x(tick.index)} y={plotH + 15} fill="#a8a49a" fontSize={10} fontWeight={700} textAnchor="middle">
                  {tick.label}
                </text>
              </g>
            ))}
            {hasOutcomes && (
              <>
                <text x={WIDTH - VALUE_W + 58} y={plotH + 15} fill="#a8a49a" fontSize={9} fontWeight={700} textAnchor="end">
                  {t("학습")}
                </text>
                <text x={WIDTH - 4} y={plotH + 15} fill="#a8a49a" fontSize={9} fontWeight={700} textAnchor="end">
                  {t("검증 CAGR")}
                </text>
              </>
            )}
            {spans.map((span, row) => {
              const y = row * ROW_H + (ROW_H - BAR_H) / 2;
              const outcome = byWindow.get(span.window);
              return (
                <g key={span.window} data-testid={`walk-forward-schedule-row-${span.window}`}>
                  <text x={0} y={y + BAR_H - 1} fill="#a8a49a" fontSize={10} fontWeight={800} fontFamily="ui-monospace, monospace">
                    W{span.window}
                  </text>
                  <rect x={x(span.isStart)} y={y} width={Math.max(1, x(span.isEnd) - x(span.isStart))} height={BAR_H} rx={3} fill={TRAIN_COLOR} opacity={0.85}>
                    <title>{`W${span.window} ${t("학습")} ${dates[span.isStart] ?? span.isStart} ~ ${dates[span.isEnd - 1] ?? span.isEnd - 1}`}</title>
                  </rect>
                  <rect x={x(span.oosStart)} y={y} width={Math.max(1, x(span.oosEnd) - x(span.oosStart))} height={BAR_H} rx={3} fill={VALIDATION_COLOR}>
                    <title>{`W${span.window} ${t("검증")} ${dates[span.oosStart] ?? span.oosStart} ~ ${dates[span.oosEnd - 1] ?? span.oosEnd - 1}`}</title>
                  </rect>
                  {outcome && (
                    <>
                      <text x={WIDTH - VALUE_W + 58} y={y + BAR_H - 1} fill="#f4f1ea" fontSize={10} fontWeight={700} textAnchor="end">
                        {fmtCagr(outcome.isCagr)}
                      </text>
                      <text
                        x={WIDTH - 4}
                        y={y + BAR_H - 1}
                        fill={outcome.oosCagr == null ? "#a8a49a" : outcome.oosCagr > 0 ? "rgb(239, 68, 68)" : "rgb(55, 122, 244)"}
                        fontSize={10}
                        fontWeight={800}
                        textAnchor="end"
                      >
                        {fmtCagr(outcome.oosCagr)}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <p className="px-3 pb-2.5 pt-1 text-[10px] font-bold leading-4 text-[var(--text-label)]">
        {anchor
          ? t("확장 방식: 학습 창의 시작은 첫 거래일에 고정되고, 창마다 끝이 검증 길이({0}거래일)만큼 늘어납니다. 검증 구간끼리는 겹치지 않으며, 이어 붙이면 처음 보는 데이터만으로 만든 성과가 됩니다.", validationBars.toLocaleString())
          : t("롤링 방식: 학습 {0}거래일 · 검증 {1}거래일 창이 검증 길이만큼씩 함께 이동합니다. 검증 구간끼리는 겹치지 않으며, 이어 붙이면 처음 보는 데이터만으로 만든 성과가 됩니다.", trainBars.toLocaleString(), validationBars.toLocaleString())}
      </p>
    </div>
  );
});

export default WalkForwardScheduleNode;
