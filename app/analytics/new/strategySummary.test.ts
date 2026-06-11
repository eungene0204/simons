import { describe, expect, it } from "vitest";
import {
  buildStrategySummary,
  buildStrategySummaryFromDsl,
  formatFundamentalFilter,
  formatInitialCapital,
  FUNDAMENTAL_FILTER_SECTION_LABEL,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  type ParsedSummary,
} from "./strategySummary";

const baseParsed: ParsedSummary = {
  description: "테스트 전략",
  universe: ["KOSPI"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

describe("strategySummary", () => {
  it("재무 조건 섹션도 UI에서는 진입 신호로 표시한다", () => {
    expect(FUNDAMENTAL_FILTER_SECTION_LABEL).toBe("진입 신호");
  });

  it("시총 배지는 원 단위 숫자를 한글 단위(억/조)로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 10_000_000_000 }))
      .toBe("시총 >= 100억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 1_000_000_000_000 }))
      .toBe("시총 >= 1조");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 300_000_000_000 }))
      .toBe("시총 >= 3,000억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: "<=", value: 1_500_000_000_000 }))
      .toBe("시총 <= 1조 5,000억");
  });

  it("시총 외 지표(PER 등)는 숫자를 그대로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "per", operator: "<=", value: 10 })).toBe("PER <= 10");
    expect(formatFundamentalFilter({ metric: "roe_or_gpa", operator: ">=", value: 15 })).toBe("ROE >= 15");
  });

  it("거래대금 배지는 억 단위 숫자에 '억'을 붙여 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "trading_value", operator: ">=", value: 50 }))
      .toBe("거래대금 >= 50억");
    expect(formatFundamentalFilter({ metric: "trading_value", operator: ">=", value: 1000 }))
      .toBe("거래대금 >= 1,000억");
  });

  it("초기자금 배지는 1억 이상이면 한글 단위(억/조)로 표시한다", () => {
    expect(formatInitialCapital(5_000_000_000)).toBe("50억원");
    expect(formatInitialCapital(1_000_000_000_000)).toBe("1조원");
  });

  it("초기자금 배지는 1억 미만이면 콤마 포함 원 단위로 표시한다", () => {
    expect(formatInitialCapital(10_000_000)).toBe("10,000,000원");
  });

  it("실행 심볼 수가 KOSPI 규모면 KOSPI200 대신 KOSPI로 표시한다", () => {
    const labels = getDisplayUniverseLabels(
      { ...baseParsed, universe: ["KOSPI200"] },
      { symbols: Array.from({ length: 800 }, (_, index) => `${index}`) }
    );

    expect(labels).toEqual(["KOSPI"]);
  });

  it("기술적 청산 신호와 리스크 레이블을 함께 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "cci" }],
      take_profit_pct: 10,
    });

    expect(labels).toEqual(["CCI", "익절 10% 이상 수익시 매도"]);
  });

  it("손절은 청산 신호 라벨에도 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 8,
    });

    expect(labels).toEqual(["MA 크로스", "손절 -8% 하락시 매도"]);
  });

  it("트레일링 스탑과 최대 보유기간도 청산 신호 라벨에 포함한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      trailing_stop_pct: 10,
      hold_period_days: 20,
    });

    expect(labels).toEqual([
      "트레일링 스탑 -10% 하락시 매도",
      "최대 20일 보유 후 매도",
    ]);
  });

  it("sell 문맥의 AI 신호는 청산 요약에서 하락 예측으로 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "ai_model", signal_type: "sell" }],
    });

    expect(labels).toEqual(["AI 하락 예측"]);
  });

  it("익절과 손절이 모두 있으면 전략 요약에도 같은 문구를 반영한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      stop_loss_pct: 7,
      take_profit_pct: 10,
    });

    expect(summary?.exitBlocks).toEqual([
      "손절 -7% 하락시 매도",
      "익절 10% 이상 수익시 매도",
    ]);
    expect(summary?.riskText).toBe("손절 7%, 익절 10%");
  });

  it("리스크 기반 청산이 없으면 기존 기술적 청산 레이블을 유지한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      exit_signals: [{ indicator: "cci" }],
    });

    expect(summary?.exitBlocks).toEqual(["CCI"]);
  });

  it("DSL 전략에서도 생성 모달용 요약 칩 정보를 만든다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-1",
      name: "테스트 전략",
      description: "사용자 프롬프트 원문",
      version: "1",
      universe: {
        id: "kospi",
        filters: {},
      },
      entry: {
        conditions: [{ id: "ma_crossover", type: "indicator", params: {} }],
      },
      exit: {
        conditions: [],
      },
      risk: {
        position_size_pct: 20,
        max_positions: 8,
        stop_loss_pct: 12,
        take_profit_pct: 10,
        max_holding_days: 182,
      },
      created_at: "",
      updated_at: "",
    });

    expect(summary?.universeName).toBe("KOSPI");
    expect(summary?.exitBlocks).toEqual([
      "손절 -12% 하락시 매도",
      "익절 10% 이상 수익시 매도",
      "최대 182일 보유 후 매도",
    ]);
    expect(summary?.positionText).toBe("포지션/비중 최대 8종목 · 182일 보유");
    expect(summary?.riskText).toBe("손절 12%, 익절 10%");
  });

  it("legacy 전략은 description에서 유니버스를 추론한다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-legacy",
      name: "PBR전략",
      description: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 고릅니다.",
      version: "1",
      universe: "" as any,
      entry: {
        conditions: [],
      },
      exit: {
        conditions: [],
      },
      risk: {
        position_size_pct: 20,
        max_positions: 8,
      },
      created_at: "",
      updated_at: "",
      symbols: Array.from({ length: 700 }, (_, index) => `${index}`),
    } as any);

    expect(summary?.universeName).toBe("KOSPI");
  });
});
