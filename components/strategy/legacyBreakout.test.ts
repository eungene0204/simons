import { describe, expect, it } from "vitest";
import {
  hasLegacyBreakoutLookback,
  inferBacktestOptionsFromResult,
  normalizeLegacyBreakoutReason,
  normalizeLegacyBreakoutStrategy,
  resolveTradeReason,
} from "@/components/strategy/legacyBreakout";
import { BacktestResult, StrategyDSL } from "@/types/strategy";

function makeStrategy(lookbackPeriod: number): StrategyDSL {
  return {
    id: "strategy_1",
    name: "Legacy breakout",
    description: "",
    version: "1.0.0",
    universe: {
      id: "kospi",
      filters: {},
    },
    entry: {
      conditions: [
        {
          type: "indicator",
          id: "breakout",
          params: { lookbackPeriod, signalType: "buy" },
        },
      ],
    },
    exit: {
      conditions: [],
    },
    risk: {
      position_size_pct: 10,
      max_positions: 5,
    },
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  };
}

function makeResult(tradingDays: number): BacktestResult {
  const dates = Array.from({ length: tradingDays }, (_, idx) => `2025-01-${String((idx % 28) + 1).padStart(2, "0")}`);

  return {
    executionId: "exec_1",
    strategyId: "strategy_1",
    totalReturn: 0,
    cagr: 0,
    buyAndHoldReturn: 0,
    maxDrawdown: 0,
    winRate: 0,
    profitFactor: 0,
    sharpe: 0,
    sortino: 0,
    volatility: 0,
    kelly: 0,
    trades: 0,
    finalEquity: 10_000_000,
    initialCapital: 10_000_000,
    equity: Array.from({ length: tradingDays }, () => 10_000_000),
    dates,
    tradesList: [],
    monthlyReturns: {},
    yearlyReturns: {},
    signals: [],
  };
}

describe("legacy breakout normalization", () => {
  it("detects breakout lookback 52 as legacy data", () => {
    expect(hasLegacyBreakoutLookback(makeStrategy(52))).toBe(true);
    expect(hasLegacyBreakoutLookback(makeStrategy(20))).toBe(false);
  });

  it("normalizes legacy breakout lookback to 252", () => {
    const normalized = normalizeLegacyBreakoutStrategy(makeStrategy(52));

    expect(normalized.entry.conditions[0].params.lookbackPeriod).toBe(252);
  });

  it("normalizes displayed legacy breakout reasons", () => {
    expect(normalizeLegacyBreakoutReason("52일 신고가 돌파")).toBe("52주 신고가 돌파");
    expect(normalizeLegacyBreakoutReason("52일 신저가 돌파")).toBe("52주 신저가 돌파");
    expect(normalizeLegacyBreakoutReason("252일 신고가 돌파")).toBe("52주 신고가 돌파");
    expect(normalizeLegacyBreakoutReason("252일 신저가 돌파")).toBe("52주 신저가 돌파");
    expect(normalizeLegacyBreakoutReason("20일 신고가 돌파")).toBe("20일 신고가 돌파");
  });

  it("expands generic sell reasons from exit conditions when possible", () => {
    expect(
      resolveTradeReason("전략 매도 조건 충족", "sell", {
        exit: {
          conditions: [
            {
              type: "indicator",
              id: "breakout",
              params: { lookbackPeriod: 252, signalType: "sell" },
            },
          ],
        },
      } as any)
    ).toBe("52주 신저가 돌파 충족");

    expect(
      resolveTradeReason("전략 매도 조건 충족", "sell", {
        exit: {
          conditions: [
            {
              type: "indicator",
              id: "rsi",
              params: { period: 14, operator: ">", value: 70, signalType: "sell" },
            },
            {
              type: "indicator",
              id: "ma_crossover",
              params: { shortMA: 5, longMA: 20, crossType: "dead", signalType: "sell" },
            },
          ],
        },
      } as any)
    ).toBe("설정된 매도 규칙 중 하나 충족 (RSI(14) > 70 / 5일/20일 데드크로스)");

    expect(resolveTradeReason("익절 10% 도달", "sell", makeStrategy(52))).toBe("익절 10% 도달");
  });

  it("infers stop loss and take profit from generic sell reasons with pnl details", () => {
    expect(
      resolveTradeReason("전략 매도 조건 충족 [수익률: -32.90%, 손실: 217,090원]", "sell", {
        exit: { conditions: [] },
        risk: { stop_loss_pct: 10 },
      } as any)
    ).toBe("손절 -10% 도달 [수익률: -32.90%, 손실: 217,090원]");

    expect(
      resolveTradeReason("전략 매도 조건 충족 [수익률: +22.40%, 수익: 217,090원]", "sell", {
        exit: { conditions: [] },
        risk: { take_profit_pct: 20 },
      } as any)
    ).toBe("익절 +20% 도달 [수익률: +22.40%, 수익: 217,090원]");
  });

  it("infers backtest options from short and long result spans", () => {
    expect(inferBacktestOptionsFromResult(makeResult(240)).period).toBe("1Y");
    expect(inferBacktestOptionsFromResult(makeResult(800)).period).toBe("3Y");
    expect(inferBacktestOptionsFromResult(makeResult(1700)).period).toBe("FULL");
  });
});
