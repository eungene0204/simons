import { t } from "@/lib/i18n";
// 결과 수치 질문(RESULT_EXPLAIN)에 넘길 사실 블록.
//
// **사실은 화면이 만들고 LLM은 설명만 한다.** 주입 없이 질문만 넘기면 LLM이 사용자의
// 결과가 아닌 남의 숫자를 지어낸다(2026-08-11 커버리지 프로브에서 드러난 구멍).
//
// 값이 없는 지표는 줄을 만들지 않는다 — 빈 자리를 0으로 채우면 "거래가 0건"처럼
// 사실과 다른 진술이 되고, LLM은 그걸 사실로 받아 설명한다.

import type { BacktestResult } from "@/types/strategy";

const percent = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;

/** 지표 하나를 "이름: 값" 줄로. 값이 유한한 수가 아니면 줄을 만들지 않는다. */
function line(label: string, value: number | null | undefined, format: (v: number) => string) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${label}: ${format(value)}`;
}

export function buildBacktestResultFacts(result: BacktestResult | null): string | null {
  if (!result) return null;
  const lines = [
    line(t("총 수익률"), result.totalReturn, percent),
    line(t("연평균 수익률(CAGR)"), result.cagr, percent),
    line(t("단순 보유(Buy&Hold) 수익률"), result.buyAndHoldReturn, percent),
    line(t("최대 낙폭(MDD)"), result.maxDrawdown, percent),
    line(t("승률"), result.winRate, (v) => `${v.toFixed(1)}%`),
    line(t("Profit Factor(총이익÷총손실)"), result.profitFactor, (v) => v.toFixed(2)),
    line(t("샤프 지수"), result.sharpe, (v) => v.toFixed(2)),
    line(t("소르티노 지수"), result.sortino, (v) => v.toFixed(2)),
    line(t("변동성"), result.volatility, (v) => `${v.toFixed(1)}%`),
    line(t("총 거래 수"), result.trades, (v) => t("{0}회", v)),
    line(t("평균 수익 거래"), result.avgProfit, percent),
    line(t("평균 손실 거래"), result.avgLoss, percent),
    line(t("평균 보유 기간"), result.avgHoldingDays, (v) => t("{0}일", v.toFixed(1))),
    line(t("최장 낙폭 기간"), result.maxDrawdownDuration, (v) => t("{0}거래일", v)),
  ].filter(Boolean);

  return lines.length > 0 ? lines.join("\n") : null;
}
