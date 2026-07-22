// 백테스트 최소 조건 게이트(프론트) — 유니버스·진입·청산·손절·익절이 모두 갖춰졌는지 판정한다.
// [정책 2026-07-22] 조건이 비면 "현재 상태로도 실행 가능"으로 넘기지 않고 채우도록 가이드하며,
// 다 채우기 전엔 '백테스트 실행' 버튼을 숨긴다. 백엔드 detect_incomplete_backtest_conditions와
// 동일한 규칙(진입은 랭킹·재무필터·지정 종목도 인정, 청산은 매도신호·보유기간·정기 리밸런싱)을
// 프론트에도 두어, 백엔드 clarification 라우팅과 무관하게 버튼 노출을 확실히 막는다.

import type { ParsedSummary } from "@/lib/strategy-summary";

function nonEmpty(value: unknown): boolean {
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

export function isBacktestReady(parsed: ParsedSummary | undefined | null): boolean {
  if (!parsed) return false;

  const hasUniverse =
    nonEmpty(parsed.universe) || nonEmpty(parsed.target_symbols) || nonEmpty(parsed.sector);
  const hasEntry =
    nonEmpty(parsed.entry_signals) ||
    nonEmpty(parsed.fundamental_filters) ||
    Boolean(parsed.ranking_metric) ||
    nonEmpty(parsed.target_symbols);
  const rebal = parsed.rebalancing_period;
  const hasRebalancing = Boolean(rebal && rebal !== "none");
  const hasExit =
    nonEmpty(parsed.exit_signals) || Boolean(parsed.hold_period_days) || hasRebalancing;
  const hasStop = parsed.stop_loss_pct != null && parsed.stop_loss_pct > 0;
  const hasTake = parsed.take_profit_pct != null && parsed.take_profit_pct > 0;
  // 단독 종목이 아니면(유니버스/다종목) 리밸런싱 주기도 필수다(단독 종목은 교체가 없어 제외).
  const isSingleAsset = nonEmpty(parsed.target_symbols);
  const rebalancingOk = isSingleAsset || hasRebalancing;

  return hasUniverse && hasEntry && hasExit && hasStop && hasTake && rebalancingOk;
}
