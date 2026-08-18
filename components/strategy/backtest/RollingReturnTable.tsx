"use client";

import type { ReactNode } from "react";
import { t } from "@/lib/i18n";
import type { RollingWindowStats } from "./rollingReturns";
import { rollingWindowLabel } from "./rollingReturnLabels";

interface Props {
  rows: RollingWindowStats[];
  /** 표 위에 놓는 라인 차트(선택한 투자 기간의 전체 구간 롤링 수익률) — 대시보드가 BacktestChart로 채운다. */
  chart?: ReactNode;
}

function pct(v: number, signed = true): string {
  if (!Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function returnColorClass(v: number): string {
  if (v > 0) return "text-[var(--main-red)]";
  if (v < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

const TH = "px-3 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-600 whitespace-nowrap";
const TD = "px-3 py-3 text-right text-sm font-black tabular-nums font-outfit whitespace-nowrap";

function windowRange(w: { start: string; end: string }): string {
  return `${w.start} ~ ${w.end}`;
}

/**
 * 롤링 수익률 표 — 투자 기간(1개월·3개월·6개월·1년·2년·3년)별로 매 거래일 진입한
 * 롤링 구간의 수익률 분포(평균·중앙값·최저·최고·손실 비율)와 구간 안 MDD(평균·최악)를 보인다.
 * 라인 차트 하나 대신 표로 보여 달라는 2026-08-18 사용자 지시 — 표 위에는 선택 기간의 전체 구간 라인 차트(chart)를 함께 둔다.
 */
export default function RollingReturnTable({ rows, chart }: Props) {
  if (rows.length === 0) {
    return (
      <div className="px-4 py-16 text-center text-sm text-gray-500">
        {t("백테스트 기간이 짧아 롤링 수익률을 계산할 수 없습니다. (최소 1개월 필요)")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="rolling-return-section">
      {chart}
      <div className="w-full overflow-x-auto">
        <table className="w-full min-w-[960px] border-collapse" data-testid="rolling-return-table">
          <thead>
            <tr>
              <th className="py-2 pl-2 pr-4 text-left text-xs font-bold uppercase tracking-widest text-gray-600 whitespace-nowrap">{t("투자 기간")}</th>
              <th className={TH}>{t("구간 수")}</th>
              <th className={TH}>{t("평균 수익률")}</th>
              <th className={TH}>{t("중앙값")}</th>
              <th className={TH}>{t("최저 수익률")}</th>
              <th className={TH}>{t("최고 수익률")}</th>
              <th className={TH}>{t("손실 구간 비율")}</th>
              <th className={TH}>{t("평균 MDD")}</th>
              <th className={TH}>{t("최악 MDD")}</th>
            </tr>
            <tr><td colSpan={9}><div className="border-t border-white/[0.05]" /></td></tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {rows.map((row) => (
              <tr
                key={row.windowMonths}
                data-testid={`rolling-row-${row.windowMonths}`}
                className="transition-colors duration-150 hover:bg-white/[0.02]"
              >
                <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">
                  {rollingWindowLabel(row.windowMonths)}
                </td>
                <td className={`${TD} text-white`}>{row.count.toLocaleString()}</td>
                <td className={`${TD} ${returnColorClass(row.meanReturn)}`}>{pct(row.meanReturn)}</td>
                <td className={`${TD} ${returnColorClass(row.medianReturn)}`}>{pct(row.medianReturn)}</td>
                <td className={`${TD} ${returnColorClass(row.minReturn)}`}>
                  {pct(row.minReturn)}
                  <span className="block text-[10px] font-medium text-gray-600">{windowRange(row.minReturnWindow)}</span>
                </td>
                <td className={`${TD} ${returnColorClass(row.maxReturn)}`}>
                  {pct(row.maxReturn)}
                  <span className="block text-[10px] font-medium text-gray-600">{windowRange(row.maxReturnWindow)}</span>
                </td>
                <td className={`${TD} text-white`}>{pct(row.lossRatio, false)}</td>
                <td className={`${TD} ${returnColorClass(row.meanMdd)}`}>{pct(row.meanMdd, false)}</td>
                <td className={`${TD} ${returnColorClass(row.worstMdd)}`}>
                  {pct(row.worstMdd, false)}
                  <span className="block text-[10px] font-medium text-gray-600">{windowRange(row.worstMddWindow)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] leading-relaxed text-gray-600">
        {t("* 각 행은 매 거래일에 진입해 해당 기간 보유했을 때의 구간(창) 수익률 분포입니다. 월별 표(달력 기준)와 달리 구간이 서로 겹치는 롤링 지표로, 진입 시점 선택에 따른 성과 변동을 보여줍니다. MDD는 각 구간 안에서 구간 시작을 첫 고점으로 삼아 잰 최대 낙폭이며, 백테스트 시작 이전으로 나가는 불완전 구간은 제외합니다.")}
      </p>
    </div>
  );
}
