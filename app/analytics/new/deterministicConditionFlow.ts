import type { ParsedSummary } from "./strategySummary";
import type { MissingBacktestCondition } from "./backtestReadiness";

export type DeterministicConditionChoice = {
  parsed: ParsedSummary;
  allowNoRebalancing?: boolean;
};

const UNIVERSE_BY_CHOICE: Record<string, string[]> = {
  코스피200: ["KOSPI200"],
  코스피: ["KOSPI"],
  코스닥: ["KOSDAQ"],
  "코스피+코스닥": ["KOSPI", "KOSDAQ"],
};

const REBALANCING_BY_CHOICE: Record<string, string> = {
  "매주 리밸런싱": "weekly",
  "매월 리밸런싱": "monthly",
  "분기마다 리밸런싱": "quarterly",
  "안 함": "none",
};

const PERIOD_BY_CHOICE: Record<string, string> = {
  "최근 1년 데이터": "1y",
  "최근 3년 데이터": "3y",
  "최근 5년 데이터": "5y",
  "사용 가능한 전체 데이터": "full",
};

const INITIAL_CAPITAL_BY_CHOICE: Record<string, number> = {
  "500만원": 5_000_000,
  "1,000만원": 10_000_000,
  "3,000만원": 30_000_000,
  "5,000만원": 50_000_000,
};

function parseFirstNumber(choice: string): number | null {
  const match = choice.replace(/,/g, "").match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

export function applyDeterministicConditionChoice({
  parsed,
  condition,
  choice,
}: {
  parsed: ParsedSummary;
  condition: MissingBacktestCondition;
  choice: string;
}): DeterministicConditionChoice | null {
  if (condition.field === "universe") {
    const universe = UNIVERSE_BY_CHOICE[choice];
    return universe ? { parsed: { ...parsed, universe } } : null;
  }

  if (condition.field === "entry") {
    if (choice === "골든크로스 발생 시 매수") {
      return {
        parsed: {
          ...parsed,
          entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
        },
      };
    }
    if (choice === "PBR 1 이하") {
      return {
        parsed: {
          ...parsed,
          fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
        },
      };
    }
    if (choice === "RSI 30 이하에서 매수") {
      return {
        parsed: {
          ...parsed,
          entry_signals: [{
            indicator: "rsi",
            signal_type: "buy",
            operator: "<=",
            value: 30,
          }],
        },
      };
    }
    return null;
  }

  if (condition.field === "exit") {
    if (choice === "데드크로스 발생 시 매도") {
      return {
        parsed: {
          ...parsed,
          exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
        },
      };
    }
    if (choice === "20일 보유 후 청산") {
      return { parsed: { ...parsed, hold_period_days: 20 } };
    }
    if (choice === "RSI 70 이상에서 매도") {
      return {
        parsed: {
          ...parsed,
          exit_signals: [{
            indicator: "rsi",
            signal_type: "sell",
            operator: ">=",
            value: 70,
          }],
        },
      };
    }
    return null;
  }

  if (condition.field === "max_positions") {
    const maxPositions = parseFirstNumber(choice);
    return maxPositions
      ? { parsed: { ...parsed, max_positions: maxPositions } }
      : null;
  }

  if (condition.field === "rebalancing") {
    const rebalancingPeriod = REBALANCING_BY_CHOICE[choice];
    return rebalancingPeriod
      ? {
          parsed: { ...parsed, rebalancing_period: rebalancingPeriod },
          allowNoRebalancing: rebalancingPeriod === "none",
        }
      : null;
  }

  if (condition.field === "stop_loss") {
    const stopLossPct = parseFirstNumber(choice);
    return stopLossPct
      ? { parsed: { ...parsed, stop_loss_pct: stopLossPct } }
      : null;
  }

  if (condition.field === "take_profit") {
    const takeProfitPct = parseFirstNumber(choice);
    return takeProfitPct
      ? { parsed: { ...parsed, take_profit_pct: takeProfitPct } }
      : null;
  }

  if (condition.field === "backtest_period") {
    const backtestPeriod = PERIOD_BY_CHOICE[choice];
    return backtestPeriod
      ? { parsed: { ...parsed, backtest_period: backtestPeriod } }
      : null;
  }

  if (condition.field === "initial_capital") {
    const initialCapital = INITIAL_CAPITAL_BY_CHOICE[choice];
    return initialCapital
      ? { parsed: { ...parsed, initial_capital: initialCapital } }
      : null;
  }

  return null;
}
