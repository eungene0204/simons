import type { ParsedSummary } from "./strategySummary";
import type { MissingBacktestCondition } from "./backtestReadiness";

export type DeterministicConditionChoice = {
  parsed: ParsedSummary;
  allowNoRebalancing?: boolean;
  /** 사용자가 '안 함'으로 거부한 슬롯 — 값이 아니라 "비어 있는 채로 확정"이라
   *  parsed에는 흔적이 남지 않는다(호출자가 거부 목록에 누적한다). */
  declinedField?: MissingBacktestCondition["field"];
};

/** 손절·익절 '안 함' 칩의 문구. 프론트 칩은 질문이 이미 필드를 말하므로 "안 함"이고,
 *  백엔드가 낸 질문의 칩은 자기완결 표기("손절 안 함")다 — 어느 쪽이 떠 있었든 클릭
 *  결과는 같아야 하므로 둘 다 받는다(백엔드 DECLINE_CHIP_FIELDS와 짝). */
const DECLINE_CHOICES: Record<string, readonly string[]> = {
  stop_loss: ["안 함", "손절 안 함"],
  take_profit: ["안 함", "익절 안 함"],
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

const ENTRY_SIGNAL_BY_CHOICE: Record<
  string,
  ParsedSummary["entry_signals"][number]
> = {
  // 기간을 칩 라벨·값에 모두 명시한다 — 기간 없는 신호는 엔진 기본값(5/20)으로 조용히
  // 돌면서 요약 카드에 드러나지 않았고, 수정 이관 라운드트립 불일치의 씨앗이었다
  // (2026-07-26 제주반도체 사고). 값은 엔진 실효 기본값과 동일해 백테스트 결과 불변.
  "골든크로스(5일/20일) 발생 시 매수": {
    indicator: "ma_crossover",
    signal_type: "buy",
    short_period: 5,
    long_period: 20,
  },
  "RSI 30 이하에서 매수": {
    indicator: "rsi",
    signal_type: "buy",
    operator: "<=",
    value: 30,
  },
  "MACD 골든크로스 매수": {
    indicator: "macd",
    signal_type: "buy",
    mode: "crossover",
  },
  "볼린저밴드 하단 터치 시 매수": {
    indicator: "bollinger_bands",
    signal_type: "buy",
  },
  "20일 고점 돌파 시 매수": {
    indicator: "breakout",
    signal_type: "buy",
    lookback_period: 20,
  },
  "거래량 급증 시 매수": { indicator: "volume_spike", signal_type: "buy" },
};

const ENTRY_FILTER_BY_CHOICE: Record<
  string,
  ParsedSummary["fundamental_filters"][number]
> = {
  "PER 10 이하": { metric: "per", operator: "<=", value: 10 },
  // metric은 백엔드 스키마(FundamentalFilter.metric)의 정본 값을 쓴다 — 'roe' 같은 근사
  // 표기를 프론트 상태에 쓰면 그 오염이 previous_parsed로 되돌아가 이후 모든 수정 요청을
  // 검증 실패시킨다(2026-07-26 사고). 백엔드 별칭 정규화는 안전망이지 오염원의 면허가 아니다.
  "ROE 15% 이상": { metric: "roe_or_gpa", operator: ">=", value: 15 },
  "PBR 1 이하": { metric: "pbr", operator: "<=", value: 1 },
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
    const entrySignal = ENTRY_SIGNAL_BY_CHOICE[choice];
    if (entrySignal) {
      return { parsed: { ...parsed, entry_signals: [entrySignal] } };
    }
    const entryFilter = ENTRY_FILTER_BY_CHOICE[choice];
    if (entryFilter) {
      return { parsed: { ...parsed, fundamental_filters: [entryFilter] } };
    }
    return null;
  }

  if (condition.field === "exit") {
    if (choice === "데드크로스(5일/20일) 발생 시 매도") {
      return {
        parsed: {
          ...parsed,
          exit_signals: [{
            indicator: "ma_crossover",
            signal_type: "sell",
            short_period: 5,
            long_period: 20,
          }],
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
    if (!maxPositions) return null;
    // 분위 그룹 전략(FR-BT-060b)에서 종목 수 답변은 '그룹당 보유 상한'이다 — 이미
    // 추출된 값의 자리 배정일 뿐 새 해석이 아니다(백엔드 _apply_prompt_overrides와 동형).
    if (parsed.ranking_quantile_groups) {
      return {
        parsed: {
          ...parsed,
          max_positions: maxPositions,
          ranking_group_cap: maxPositions,
        },
      };
    }
    return { parsed: { ...parsed, max_positions: maxPositions } };
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

  if (condition.field === "stop_loss" || condition.field === "take_profit") {
    // '안 함'은 값을 넣지 않고 그 슬롯을 거부로 확정한다 — 값 추출을 먼저 시도하면
    // 숫자가 없어 null(=미적용)로 떨어져 같은 질문이 반복된다.
    if (DECLINE_CHOICES[condition.field].includes(choice.trim())) {
      return { parsed, declinedField: condition.field };
    }
    const pct = parseFirstNumber(choice);
    if (!pct) return null;
    return condition.field === "stop_loss"
      ? { parsed: { ...parsed, stop_loss_pct: pct } }
      : { parsed: { ...parsed, take_profit_pct: pct } };
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
