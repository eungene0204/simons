import { describe, expect, it } from "vitest";
import {
  buildStrategySummary,
  buildStrategySummaryFromDsl,
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
  backtest_period: "5y",
  initial_capital: 10000000,
};

describe("strategySummary", () => {
  it("실행 심볼 수가 KOSPI 규모면 KOSPI200 대신 KOSPI로 표시한다", () => {
    const labels = getDisplayUniverseLabels(
      { ...baseParsed, universe: ["KOSPI200"] },
      { symbols: Array.from({ length: 800 }, (_, index) => `${index}`) }
    );

    expect(labels).toEqual(["KOSPI"]);
  });

  it("익절이 있으면 기술적 지표 대신 사용자 친화적 청산 문구를 우선 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "cci" }],
      take_profit_pct: 10,
    });

    expect(labels).toEqual(["익절 10% 이상 수익시 매도"]);
  });

  it("익절과 손절이 모두 있으면 전략 요약에도 같은 문구를 반영한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      stop_loss_pct: 7,
      take_profit_pct: 10,
    });

    expect(summary?.exitBlocks).toEqual([
      "익절 10% 이상 수익시 매도",
      "손절 7% 하락시 매도",
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
      "익절 10% 이상 수익시 매도",
      "손절 12% 하락시 매도",
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
