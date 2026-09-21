// 가상계좌 정액 적립식(2026-09-21)의 순수 계산 — 서버·클라이언트 공용.
//
// 적립 계좌는 초기 자본 이후에도 돈이 들어온다. 수익률의 분모를 초기 자본으로 두면 납입액이
// 전부 수익으로 세어지므로, 계좌 수익률은 **총 납입액**(초기 자본 + 누적 납입) 기준이다.
// 납입이 없는 계좌는 누적 납입이 0이라 종전 값과 같다.

type Numeric = number | string | { toString(): string } | null | undefined;

const num = (value: Numeric): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

/** 수익률의 분모 — 초기 자본 + 누적 납입액. */
export function totalContributed(initialCash: Numeric, contributedCash: Numeric): number {
  return num(initialCash) + num(contributedCash);
}

/**
 * 전략이 정액 적립식이면 계좌의 시작 자본(전략의 초기 자본, 플랜 투자금 이하)을, 아니면 null을 준다.
 * 판정은 백엔드(backtest_engine·virtual_trader)와 같다 — 납입액·주기가 둘 다 있는 지정 종목 전략.
 */
export function contributionStartCapital(
  strategySettings: string | null | undefined,
  planAmount: number,
): number | null {
  if (!strategySettings) return null;
  let dsl: any;
  try {
    dsl = JSON.parse(strategySettings);
  } catch {
    return null;
  }
  const risk = dsl?.risk ?? {};
  const isPlan =
    num(risk.contribution_amount) > 0 &&
    Boolean(risk.contribution_period) &&
    dsl?.backtest_mode === "single_asset";
  if (!isPlan) return null;
  const initial = num(risk.init_cash);
  return initial > 0 ? Math.min(initial, planAmount) : planAmount;
}
