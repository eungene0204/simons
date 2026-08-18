import { BacktestResult, Condition, StrategyDSL } from "@/types/strategy";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import { t } from "@/lib/i18n";

function normalizeLegacyBreakoutCondition(condition: Condition): Condition {
  if (condition.id !== "breakout" || condition.params?.lookbackPeriod !== 52) {
    return condition;
  }

  return {
    ...condition,
    params: {
      ...condition.params,
      lookbackPeriod: 252,
    },
  };
}

export function hasLegacyBreakoutLookback(strategy: Pick<StrategyDSL, "entry" | "exit"> | null | undefined): boolean {
  if (!strategy) return false;

  const conditions = [
    ...(strategy.entry?.conditions ?? []),
    ...(strategy.exit?.conditions ?? []),
  ];

  return conditions.some((condition) => (
    condition.id === "breakout" && condition.params?.lookbackPeriod === 52
  ));
}

export function normalizeLegacyBreakoutStrategy<T extends Pick<StrategyDSL, "entry" | "exit">>(strategy: T): T {
  if (!hasLegacyBreakoutLookback(strategy)) {
    return strategy;
  }

  return {
    ...strategy,
    entry: {
      ...strategy.entry,
      conditions: (strategy.entry?.conditions ?? []).map(normalizeLegacyBreakoutCondition),
    },
    exit: {
      ...strategy.exit,
      conditions: (strategy.exit?.conditions ?? []).map(normalizeLegacyBreakoutCondition),
    },
  };
}

export function normalizeLegacyBreakoutReason(reason: string | null | undefined): string | null | undefined {
  if (!reason) return reason;

  return reason
    .replaceAll("252일 신고가 돌파", "52주 신고가 돌파")
    .replaceAll("252일 신저가 돌파", "52주 신저가 돌파")
    .replaceAll("52일 신고가 돌파", "52주 신고가 돌파")
    .replaceAll("52일 신저가 돌파", "52주 신저가 돌파");
}

function formatBreakoutPeriodLabel(lookbackPeriod: number | undefined): string {
  if (lookbackPeriod === 252) return t("52주");
  if (!lookbackPeriod) return t("기준 기간");
  return t("{0}일", lookbackPeriod);
}

function describeExitCondition(condition: Condition): string {
  switch (condition.id) {
    case "breakout": {
      const lookbackPeriod = Number(condition.params?.lookbackPeriod);
      const direction = condition.params?.signalType === "sell" ? "신저가 돌파" : "신고가 돌파";
      return `${formatBreakoutPeriodLabel(lookbackPeriod)} ${direction}`;
    }
    case "ma_crossover": {
      const shortMA = condition.params?.shortMA;
      const longMA = condition.params?.longMA;
      const crossType = condition.params?.crossType === "dead" ? "데드크로스" : "골든크로스";
      if (shortMA && longMA) {
        return t("{0}일/{1}일 {2}", shortMA, longMA, crossType);
      }
      return crossType;
    }
    case "rsi": {
      const period = condition.params?.period;
      const operator = condition.params?.operator ?? "";
      const value = condition.params?.value;
      if (period && value !== undefined) {
        return `RSI(${period}) ${operator} ${value}`;
      }
      return t("RSI 조건");
    }
    default:
      return condition.id;
  }
}

function splitReasonAndDetails(reason: string): { baseReason: string; details: string } {
  const detailStart = reason.indexOf(" [수익률:");
  if (detailStart === -1) {
    return { baseReason: reason, details: "" };
  }

  return {
    baseReason: reason.slice(0, detailStart),
    details: reason.slice(detailStart),
  };
}

export function resolveTradeReason(
  reason: string | null | undefined,
  tradeType: "buy" | "sell",
  strategy: Pick<StrategyDSL, "exit"> | null | undefined
): string | null | undefined {
  const normalizedReason = normalizeLegacyBreakoutReason(reason);
  if (!normalizedReason || tradeType !== "sell") {
    return normalizedReason;
  }

  // 손절/익절 판정은 백엔드 exit_type(result_handler)만 신뢰한다. 손실률 크기로 손절을
  // 사후 추정하면 실제로는 다른 청산 조건으로 팔린 거래까지 '손절 도달'로 오귀속되므로,
  // 여기서는 재라벨하지 않고 일반 매도 사유의 청산 조건 서술까지만 수행한다.
  const { baseReason, details } = splitReasonAndDetails(normalizedReason);

  if (baseReason !== "전략 매도 조건 충족") {
    return normalizedReason;
  }

  const exitConditions = strategy?.exit?.conditions ?? [];
  if (exitConditions.length === 1) {
    return t("{0} 충족{1}", describeExitCondition(exitConditions[0]), details);
  }
  if (exitConditions.length > 1) {
    return t("설정된 매도 규칙 중 하나 충족 ({0}){1}", exitConditions.map(describeExitCondition).join(" / "), details);
  }

  return `${baseReason}${details}`;
}

export function inferBacktestOptionsFromResult(result: BacktestResult): BacktestConfigOptions {
  const tradingDays = result.dates?.length ?? 0;

  let period = "5Y";
  if (tradingDays <= 320) {
    period = "1Y";
  } else if (tradingDays <= 900) {
    period = "3Y";
  } else if (tradingDays > 1500) {
    period = "FULL";
  }

  return {
    period,
    initialCapital: result.initialCapital || 10_000_000,
    commissionPct: 0.015,
    slippagePct: 0.05,
  };
}
