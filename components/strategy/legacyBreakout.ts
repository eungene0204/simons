import { BacktestResult, Condition, StrategyDSL } from "@/types/strategy";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";

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
  if (lookbackPeriod === 252) return "52주";
  if (!lookbackPeriod) return "기준 기간";
  return `${lookbackPeriod}일`;
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
        return `${shortMA}일/${longMA}일 ${crossType}`;
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
      return "RSI 조건";
    }
    default:
      return condition.id;
  }
}

function parseTradeReturnPercent(reason: string): number | null {
  const match = reason.match(/\[수익률:\s*([+-]?\d+(?:\.\d+)?)%/);
  if (!match) return null;

  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
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

function formatRiskExitReason(
  baseReason: string,
  details: string,
  strategy: Pick<StrategyDSL, "risk"> | null | undefined,
  returnPct: number | null
): string {
  if (!strategy?.risk) {
    return `${baseReason}${details}`;
  }

  const tolerance = 1.0;
  const stopLossPct = strategy.risk.stop_loss_pct;
  const takeProfitPct = strategy.risk.take_profit_pct;

  if (
    stopLossPct &&
    returnPct !== null &&
    returnPct < 0 &&
    returnPct <= -(stopLossPct - tolerance)
  ) {
    return `손절 -${stopLossPct}% 도달${details}`;
  }

  if (
    takeProfitPct &&
    returnPct !== null &&
    returnPct > 0 &&
    returnPct >= takeProfitPct - tolerance
  ) {
    return `익절 +${takeProfitPct}% 도달${details}`;
  }

  return `${baseReason}${details}`;
}

export function resolveTradeReason(
  reason: string | null | undefined,
  tradeType: "buy" | "sell",
  strategy: Pick<StrategyDSL, "exit" | "risk"> | null | undefined
): string | null | undefined {
  const normalizedReason = normalizeLegacyBreakoutReason(reason);
  if (!normalizedReason || tradeType !== "sell") {
    return normalizedReason;
  }

  const { baseReason, details } = splitReasonAndDetails(normalizedReason);
  const returnPct = parseTradeReturnPercent(normalizedReason);

  if (baseReason === "전략 매도 조건 충족") {
    const riskResolvedReason = formatRiskExitReason(baseReason, details, strategy, returnPct);
    if (riskResolvedReason !== `${baseReason}${details}`) {
      return riskResolvedReason;
    }
  }

  if (baseReason !== "전략 매도 조건 충족") {
    return normalizedReason;
  }

  const exitConditions = strategy?.exit?.conditions ?? [];
  if (exitConditions.length === 1) {
    return `${describeExitCondition(exitConditions[0])} 충족${details}`;
  }
  if (exitConditions.length > 1) {
    return `설정된 매도 규칙 중 하나 충족 (${exitConditions.map(describeExitCondition).join(" / ")})${details}`;
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
