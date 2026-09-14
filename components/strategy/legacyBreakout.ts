import { BacktestResult, Condition, StrategyDSL } from "@/types/strategy";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import { t } from "@/lib/i18n";
import {
  REASON_TEMPLATE,
  firstReasonTemplate,
  isTradeReasonSegments,
  renderTradeReasonSegments,
  type TradeReasonSegment,
} from "@/lib/trade-reason";

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
      const periodLabel = formatBreakoutPeriodLabel(lookbackPeriod);
      return condition.params?.signalType === "sell"
        ? t("{0} 신저가 돌파", periodLabel)
        : t("{0} 신고가 돌파", periodLabel);
    }
    case "ma_crossover": {
      const shortMA = condition.params?.shortMA;
      const longMA = condition.params?.longMA;
      const crossType = condition.params?.crossType === "dead" ? t("데드크로스") : t("골든크로스");
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

/** 청산 조건 서술 — 사유가 '전략 매도 조건 충족'뿐일 때 이 문구로 바꿔 보여준다. */
function describeExitConditions(strategy: Pick<StrategyDSL, "exit"> | null | undefined): string | null {
  const exitConditions = strategy?.exit?.conditions ?? [];
  if (exitConditions.length === 1) {
    return t("{0} 충족", describeExitCondition(exitConditions[0]));
  }
  if (exitConditions.length > 1) {
    return t("설정된 매도 규칙 중 하나 충족 ({0})", exitConditions.map(describeExitCondition).join(" / "));
  }
  return null;
}

/** 252거래일 돌파는 '52주'로 읽는 것이 사용자 표기다(구조화 사유에도 같은 규칙 적용). */
function normalizeBreakoutSegments(segments: TradeReasonSegment[]): TradeReasonSegment[] {
  return segments.map((seg) => {
    if (!("t" in seg)) return seg;
    const lookback = Number((seg.a ?? [])[0]);
    if (lookback !== 252 && lookback !== 52) return seg;
    if (seg.t === REASON_TEMPLATE.breakoutHigh) return { t: REASON_TEMPLATE.breakoutHigh52w };
    if (seg.t === REASON_TEMPLATE.breakoutLow) return { t: REASON_TEMPLATE.breakoutLow52w };
    return seg;
  });
}

/**
 * 거래 내역에 표시할 매매사유.
 *
 * 엔진이 구조화 사유(reasonParts)를 주면 템플릿을 번역해 렌더링하고, 없으면(구버전 결과)
 * 백엔드가 준 한국어 문장을 종전 규칙대로 다듬어 쓴다.
 */
export function resolveTradeReasonDisplay(
  reason: string | null | undefined,
  parts: unknown,
  tradeType: "buy" | "sell",
  strategy: Pick<StrategyDSL, "exit"> | null | undefined,
  formatMoney: (value: number) => string
): string {
  if (!isTradeReasonSegments(parts) || parts.length === 0) {
    return resolveTradeReason(reason, tradeType, strategy) ?? "";
  }

  let segments = normalizeBreakoutSegments(parts);

  // 손절/익절 판정은 백엔드 exit_type(result_handler)만 신뢰한다 — 여기서는 일반 매도
  // 사유('전략 매도 조건 충족')를 전략의 청산 조건 서술로 바꾸는 일만 한다.
  if (tradeType === "sell" && firstReasonTemplate(segments) === REASON_TEMPLATE.exitStrategySignal) {
    const described = describeExitConditions(strategy);
    if (described) {
      segments = segments.map((seg) =>
        "t" in seg && seg.t === REASON_TEMPLATE.exitStrategySignal ? { s: described } : seg
      );
    }
  }

  return renderTradeReasonSegments(segments, formatMoney);
}

const rateToPct = (rate: number | null | undefined): number | undefined =>
  rate == null ? undefined : rate * 100;

export function inferBacktestOptionsFromResult(
  result: BacktestResult,
  // 저장된 DSL의 비용 옵션(소수 비율) — 결과에 적용 비용 동봉이 없는 구버전 결과의 차선.
  dslOptions?: { fee_rate?: number | null; slippage_rate?: number | null } | null,
): BacktestConfigOptions {
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
    // 이 결과가 실제로 적용한 비용(tradingCosts)이 먼저, 없으면 DSL이 실은 값, 그것도 없으면
    // 기본값 — 종전 하드코딩은 사용자가 요청한 수수료·슬리피지를 재실행에서 지웠다(2026-09-14).
    commissionPct:
      rateToPct(result.tradingCosts?.buyFeeRate) ?? rateToPct(dslOptions?.fee_rate) ?? 0.015,
    slippagePct:
      rateToPct(result.tradingCosts?.slippageRate) ?? rateToPct(dslOptions?.slippage_rate) ?? 0.05,
  };
}
