"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowsClockwise, Info, Spinner, Warning } from "phosphor-react";
import { formatProfitFactor } from "@/lib/format-profit-factor";
import { t } from "@/lib/i18n";
import {
  REBALANCE_COMPARISON_PERIODS,
  rebalancePeriodLabel,
  runRebalanceComparisonStream,
  type RebalanceComparisonAnalysis,
  type RebalanceComparisonProgress,
  type RebalanceComparisonResult,
  type RebalancePeriodRow,
} from "./rebalanceComparison";

interface Props {
  /** 엔진 백테스트 요청(BacktestRequest). 없으면 비교를 실행할 수 없다(저장 설정 없는 옛 기록). */
  backtestDsl: Record<string, any> | null | undefined;
  strategyName?: string;
  universeName?: string;
  /** 메인 결과(현재 설정)의 지표 — '현재 설정' 참고 행과 AI 입력에 쓴다. */
  currentMetrics: Record<string, number | null>;
}

type Phase =
  | { kind: "idle" }
  | { kind: "running"; progress: RebalanceComparisonProgress | null }
  | { kind: "done"; result: RebalanceComparisonResult }
  | { kind: "error"; message: string };

const RATING_STYLES: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  B: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  C: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  D: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

const RATING_LABELS: Record<string, string> = {
  A: "주기 무관 안정",
  B: "대체로 안정",
  C: "주기 민감",
  D: "특정 주기 과적합 의심",
};

type AnalysisSectionKey = keyof RebalanceComparisonAnalysis["analysis"];

const ANALYSIS_SECTIONS: Array<{ key: AnalysisSectionKey; label: string }> = [
  { key: "performance_analysis", label: "성과 비교" },
  { key: "risk_analysis", label: "리스크" },
  { key: "transaction_cost_analysis", label: "거래 비용 영향" },
  { key: "overfitting_analysis", label: "과최적화 가능성" },
];

function pct(v: number | null | undefined, signed = true): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function num(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(2);
}

function returnColorClass(v: number | null | undefined): string {
  if (v == null) return "text-gray-500";
  if (v > 0) return "text-[var(--main-red)]";
  if (v < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

/** 비교표 행 순서 — 6주기(짧은 → 긴) 뒤에 '현재 설정' 참고 행(6주기 밖일 때만). */
export function orderComparisonRows(
  rows: RebalancePeriodRow[],
  currentPeriod: string | null | undefined,
  currentMetrics: Record<string, number | null>
): Array<RebalancePeriodRow & { isCurrent: boolean; isReference: boolean }> {
  const byPeriod = new Map(rows.map((row) => [row.period, row]));
  const ordered = REBALANCE_COMPARISON_PERIODS
    .map((period) => byPeriod.get(period))
    .filter((row): row is RebalancePeriodRow => Boolean(row))
    .map((row) => ({ ...row, isCurrent: row.period === currentPeriod, isReference: false }));
  if (currentPeriod && !byPeriod.has(currentPeriod)) {
    ordered.push({
      period: currentPeriod,
      cagr: currentMetrics.cagr ?? null,
      mdd: currentMetrics.mdd ?? null,
      sharpe_ratio: currentMetrics.sharpe_ratio ?? null,
      profit_factor: currentMetrics.profit_factor ?? null,
      trade_count: currentMetrics.trade_count ?? 0,
      turnover: currentMetrics.turnover ?? null,
      isCurrent: true,
      isReference: true,
    });
  }
  return ordered;
}

export default function RebalanceComparisonSection({
  backtestDsl,
  strategyName,
  universeName,
  currentMetrics,
}: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const run = async () => {
    if (!backtestDsl) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase({ kind: "running", progress: null });
    try {
      const result = await runRebalanceComparisonStream(
        {
          // 저장된 전략 DSL에는 symbols가 없을 수 있다(유니버스는 universe_id로 저장, 엔진이 PIT
          // 마스터로 종목을 재해석). 백엔드 스키마는 symbols 필드 자체를 요구하므로 빈 배열로 채운다.
          base_strategy: { ...backtestDsl, symbols: backtestDsl.symbols ?? [] },
          strategy_name: strategyName ?? null,
          investment_universe: universeName ?? null,
          current: currentMetrics,
        },
        {
          signal: controller.signal,
          onProgress: (progress) => setPhase({ kind: "running", progress }),
        }
      );
      if (controller.signal.aborted) return;
      setPhase({ kind: "done", result });
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "error", message: error instanceof Error ? error.message : t("리밸런싱 비교 분석 실패") });
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    setPhase({ kind: "idle" });
  };

  if (!backtestDsl) {
    return (
      <div className="px-4 py-12 text-center text-sm text-gray-500">
        {t("이 기록에는 실행 당시의 백테스트 요청(진입·청산 조건, 리스크 설정)이 저장되어 있지 않아 같은 전략을 다시 실행할 수 없습니다. 전략연구소에서 백테스트를 다시 실행하면 이 탭에서 6주기 비교를 볼 수 있습니다.")}
      </div>
    );
  }

  if (phase.kind === "idle" || phase.kind === "error") {
    return (
      <div className="flex flex-col items-center gap-4 px-4 py-10 text-center">
        <p className="max-w-xl text-sm leading-relaxed text-gray-400">
          {t("같은 전략을 매일·매주·매월·분기·반기·연간 6가지 리밸런싱 주기로 다시 백테스트해 CAGR·MDD·샤프·손익비·거래 수·회전율을 비교하고, 주기 민감도와 거래 비용 영향을 분석합니다.")}
        </p>
        <p className="text-[11px] text-gray-600">
          {t("백테스트 6회와 AI 서술이 이어지므로 종목 수·기간에 따라 몇 분 걸릴 수 있습니다.")}
        </p>
        {phase.kind === "error" && (
          <p className="flex items-center gap-1.5 text-xs font-bold text-rose-300" role="alert">
            <Warning size={14} weight="bold" />
            {phase.message}
          </p>
        )}
        <button
          type="button"
          onClick={run}
          className="inline-flex min-h-[38px] items-center gap-2 rounded-[10px] bg-white px-4 text-sm font-black text-black transition-colors hover:bg-gray-200"
        >
          <ArrowsClockwise size={16} weight="bold" />
          {phase.kind === "error" ? t("다시 실행") : t("리밸런싱 기간별 비교 실행")}
        </button>
      </div>
    );
  }

  if (phase.kind === "running") {
    const progress = phase.progress;
    const total = progress?.total ?? REBALANCE_COMPARISON_PERIODS.length;
    const index = progress?.stage === "backtest" ? progress.index ?? 0 : progress?.stage === "analysis" ? total : 0;
    const ratio = progress?.stage === "analysis" ? 1 : Math.max(0, (index - 1) / total);
    const message =
      progress?.stage === "analysis"
        ? t("AI가 주기별 결과를 비교 서술하는 중…")
        : progress?.stage === "backtest"
        ? t("백테스트 실행 중 — {0} ({1}/{2})", rebalancePeriodLabel(progress.period), index, total)
        : t("준비 중…");
    return (
      <div className="flex flex-col items-center gap-4 px-4 py-12 text-center" aria-live="polite">
        <Spinner className="h-5 w-5 animate-spin text-gray-400" />
        <p className="text-sm font-bold text-gray-300">{message}</p>
        <div className="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className="h-full rounded-full bg-white/70 transition-[width] duration-500"
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </div>
        <button
          type="button"
          onClick={cancel}
          className="text-xs font-bold text-gray-500 underline-offset-2 hover:text-gray-300 hover:underline"
        >
          {t("취소")}
        </button>
      </div>
    );
  }

  const { result } = phase;
  const analysis = result.analysis ?? null;
  const rows = orderComparisonRows(result.rebalance_results ?? [], result.current_period, currentMetrics);
  const recommended = analysis?.summary.recommended_rebalance_period ?? null;
  const rating = analysis?.summary.stability_rating ?? null;
  const backtestPeriod = result.backtest_period;

  return (
    <div className="flex flex-col gap-5" data-testid="rebalance-comparison-section">
      {/* 요약 배지 */}
      {analysis && (
        <div className="flex flex-wrap items-stretch gap-2">
          <div className="flex min-w-[160px] flex-1 flex-col gap-1 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{t("데이터 기준 적합 주기")}</span>
            <span className="text-base font-black text-white">{rebalancePeriodLabel(recommended)}</span>
          </div>
          <div className="flex min-w-[160px] flex-1 flex-col gap-1 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{t("주기 안정성 등급")}</span>
            <span className="flex items-center gap-2">
              <span className={`inline-flex h-6 min-w-[24px] items-center justify-center rounded border px-1.5 text-xs font-black ${rating ? RATING_STYLES[rating] : "border-white/10 text-gray-400"}`}>
                {rating ?? "—"}
              </span>
              <span className="text-xs font-bold text-gray-300">{rating ? t(RATING_LABELS[rating]) : t("평가 없음")}</span>
            </span>
          </div>
          <div className="flex min-w-[140px] flex-1 flex-col gap-1 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{t("분석 신뢰도")}</span>
            <span className="text-base font-black tabular-nums text-white">
              {analysis.summary.confidence_score == null ? "—" : `${analysis.summary.confidence_score}/100`}
            </span>
          </div>
          <div className="flex min-w-[200px] flex-[2] flex-col gap-1 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{t("전략 성격 추론")}</span>
            <span className="text-sm font-bold leading-snug text-gray-200">{analysis.summary.strategy_character || "—"}</span>
          </div>
        </div>
      )}

      {(result.notices ?? []).map((notice) => (
        <p key={notice} className="flex items-start gap-1.5 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-xs leading-relaxed text-gray-300" role="note">
          <Info size={14} weight="bold" className="mt-0.5 shrink-0 text-gray-500" />
          {notice}
        </p>
      ))}

      {result.analysis_degraded && (
        <p className="flex items-start gap-1.5 rounded-[10px] border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2 text-xs leading-relaxed text-amber-200" role="status">
          <Warning size={14} weight="bold" className="mt-0.5 shrink-0" />
          {t("AI 서술을 생성하지 못해 주기별 수치 비교만 표시합니다. '다시 실행'으로 재시도할 수 있습니다.")}
        </p>
      )}

      {/* 비교표 */}
      <div className="w-full overflow-x-auto">
        <table className="w-full min-w-[820px] border-collapse" data-testid="rebalance-comparison-table">
          <thead>
            <tr>
              <th className="py-2 pl-2 pr-4 text-left text-xs font-bold uppercase tracking-widest text-gray-600">{t("리밸런싱 주기")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">CAGR</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">MDD</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("샤프")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("손익비")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("거래 수")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("회전율")}</th>
              {analysis && (
                <th className="py-2 pl-4 pr-2 text-left text-xs font-bold uppercase tracking-widest text-gray-600">{t("평가")}</th>
              )}
            </tr>
            <tr><td colSpan={analysis ? 8 : 7}><div className="border-t border-white/[0.05]" /></td></tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {rows.map((row) => {
              const isRecommended = !row.isReference && row.period === recommended;
              return (
                <tr
                  key={row.period}
                  data-testid={`rebalance-row-${row.period}`}
                  className={`transition-colors duration-150 hover:bg-white/[0.02] ${isRecommended ? "bg-white/[0.04]" : ""}`}
                >
                  <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">
                    {rebalancePeriodLabel(row.period)}
                    {row.isCurrent && (
                      <span className="ml-1.5 inline-flex items-center rounded bg-white/10 px-1.5 py-0.5 text-[9px] font-bold text-gray-300">
                        {t("현재 설정")}
                      </span>
                    )}
                    {isRecommended && (
                      <span className="ml-1.5 inline-flex items-center rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300">
                        {t("적합")}
                      </span>
                    )}
                  </td>
                  {row.error ? (
                    <td colSpan={analysis ? 7 : 6} className="px-3 py-3 text-xs text-rose-300">
                      {t("실행 실패: {0}", row.error)}
                    </td>
                  ) : (
                    <>
                      <td className={`px-3 py-3 text-right text-sm font-black tabular-nums font-outfit ${returnColorClass(row.cagr)}`}>{pct(row.cagr)}</td>
                      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{pct(row.mdd, false)}</td>
                      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{num(row.sharpe_ratio)}</td>
                      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{formatProfitFactor(row.profit_factor)}</td>
                      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{row.trade_count}</td>
                      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{row.turnover == null ? "—" : `${row.turnover.toFixed(1)}%`}</td>
                      {analysis && (
                        <td className="min-w-[220px] py-3 pl-4 pr-2 text-xs leading-relaxed text-gray-300">
                          {row.isReference ? t("현재 설정의 결과(참고)") : analysis.evaluations[row.period] || "—"}
                        </td>
                      )}
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] leading-relaxed text-gray-600">
        {backtestPeriod
          ? t("* 백테스트 기간 {0} ~ {1}. 각 행은 리밸런싱 주기만 바꿔 같은 전략을 다시 실행한 과거 데이터 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.", backtestPeriod.start, backtestPeriod.end)
          : t("* 각 행은 리밸런싱 주기만 바꿔 같은 전략을 다시 실행한 과거 데이터 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.")}
      </p>

      {/* AI 분석 서술 */}
      {analysis && (
        <div className="grid gap-3 md:grid-cols-2">
          {ANALYSIS_SECTIONS.map((section) => (
            <div key={section.key} className="rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3">
              <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{t(section.label)}</p>
              <p className="text-sm leading-relaxed text-gray-200">{analysis.analysis[section.key] || "—"}</p>
            </div>
          ))}
          <div className="rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-4 py-3 md:col-span-2">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">
              {t("적합 주기 판단 근거 — {0}", rebalancePeriodLabel(analysis.recommendation.recommended_period))}
            </p>
            <p className="text-sm leading-relaxed text-gray-200">{analysis.recommendation.reason || "—"}</p>
            {analysis.recommendation.warning && (
              <p className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-amber-200">
                <Warning size={14} weight="bold" className="mt-0.5 shrink-0" />
                {analysis.recommendation.warning}
              </p>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[10px] leading-relaxed text-gray-600">
          {t("* 이 분석은 사용자가 만든 전략의 리밸런싱 주기별 과거 시뮬레이션 수치를 비교한 것으로, 특정 주기의 사용을 권유하는 투자 조언이 아닙니다.")}
        </p>
        <button
          type="button"
          onClick={run}
          className="inline-flex min-h-[32px] items-center gap-1.5 rounded-[8px] border border-white/10 px-3 text-xs font-bold text-gray-300 transition-colors hover:bg-white/5 hover:text-white"
        >
          <ArrowsClockwise size={14} weight="bold" />
          {t("다시 실행")}
        </button>
      </div>
    </div>
  );
}
