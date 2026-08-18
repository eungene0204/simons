"use client";

import { useMemo, useState } from "react";
import { Info } from "phosphor-react";
import { formatProfitFactor } from "@/lib/format-profit-factor";
import { t } from "@/lib/i18n";
import {
  REBALANCE_CHART_METRICS,
  buildRebalanceChartBars,
  orderComparisonRows,
  rebalancePeriodLabel,
  type CurrentSettingMetrics,
  type RebalanceChartMetric,
  type RebalanceComparisonResult,
} from "./rebalanceComparison";
import RebalanceComparisonChart from "./RebalanceComparisonChart";

interface Props {
  /** 엔진이 백테스트 결과에 동봉한 6주기 비교. 구버전 저장 결과에는 없다. */
  data: RebalanceComparisonResult | null | undefined;
  /** 메인 결과(현재 설정)의 지표 — 현재 주기가 6주기 밖이면 참고 행으로 쓴다. */
  current: CurrentSettingMetrics;
}

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

/**
 * 리밸런싱 기간별 결과(FR-BT-064) — 같은 전략을 6주기로 재시뮬레이션한 엔진 수치 비교표.
 * 별도 실행 없이 백테스트 결과와 함께 온다(2026-08-18 사용자 지시 — 실행 버튼·AI 서술 없음).
 */
export default function RebalanceComparisonSection({ data, current }: Props) {
  const [metric, setMetric] = useState<RebalanceChartMetric>("cagr");
  const hasData = Boolean(data && Array.isArray(data.periods) && data.periods.length > 0);
  const rows = useMemo(() => (hasData && data ? orderComparisonRows(data, current) : []), [hasData, data, current]);
  const bars = useMemo(() => buildRebalanceChartBars(rows, metric), [rows, metric]);

  if (!hasData || !data) {
    return (
      <div className="px-4 py-12 text-center text-sm leading-relaxed text-gray-500">
        {t("이 결과에는 리밸런싱 기간별 비교가 저장되어 있지 않습니다. 새로 실행된 백테스트부터 함께 계산됩니다.")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="rebalance-comparison-section">
      {data.positionCapAbsent && (
        <p className="flex items-start gap-1.5 rounded-[10px] border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-xs leading-relaxed text-gray-300" role="note">
          <Info size={14} weight="bold" className="mt-0.5 shrink-0 text-gray-500" />
          {t("이 전략은 최대 보유 종목 수·비율 선정이 없어 리밸런싱 주기가 결과에 영향을 주지 않습니다 — 6주기 결과가 모두 같게 나올 수 있습니다.")}
        </p>
      )}

      {/* 막대 그래프 — 주기별 선택 지표(표와 같은 행) */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-end gap-1" role="group" aria-label={t("비교 지표 선택")}>
          {REBALANCE_CHART_METRICS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setMetric(opt.key)}
              aria-pressed={metric === opt.key}
              className={`rounded-md px-2 py-1 text-[11px] font-bold transition-colors ${
                metric === opt.key ? "bg-white/10 text-white" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {t(opt.label)}
            </button>
          ))}
        </div>
        <RebalanceComparisonChart bars={bars} metric={metric} height={220} />
      </div>

      <div className="w-full overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse" data-testid="rebalance-comparison-table">
          <thead>
            <tr>
              <th className="py-2 pl-2 pr-4 text-left text-xs font-bold uppercase tracking-widest text-gray-600">{t("리밸런싱 주기")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">CAGR</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">MDD</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("샤프")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("손익비")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("거래 수")}</th>
              <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600">{t("회전율")}</th>
            </tr>
            <tr><td colSpan={7}><div className="border-t border-white/[0.05]" /></td></tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {rows.map((row) => (
              <tr
                key={row.period}
                data-testid={`rebalance-row-${row.period}`}
                className={`transition-colors duration-150 hover:bg-white/[0.02] ${row.isCurrent ? "bg-white/[0.03]" : ""}`}
              >
                <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">
                  {rebalancePeriodLabel(row.period)}
                  {row.isCurrent && (
                    <span className="ml-1.5 inline-flex items-center rounded bg-white/10 px-1.5 py-0.5 text-[9px] font-bold text-gray-300">
                      {t("현재 설정")}
                    </span>
                  )}
                </td>
                {row.error ? (
                  <td colSpan={6} className="px-3 py-3 text-xs text-rose-300">
                    {t("실행 실패: {0}", row.error)}
                  </td>
                ) : (
                  <>
                    <td className={`px-3 py-3 text-right text-sm font-black tabular-nums font-outfit ${returnColorClass(row.cagr)}`}>{pct(row.cagr)}</td>
                    <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{pct(row.mdd, false)}</td>
                    <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{num(row.sharpe)}</td>
                    <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{formatProfitFactor(row.profitFactor)}</td>
                    <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{row.trades ?? "—"}</td>
                    <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-white">{row.turnover == null ? "—" : `${row.turnover.toFixed(1)}%`}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
