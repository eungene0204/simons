// @ts-nocheck
import { describe, expect, it } from "vitest";
import {
  buildAutoSaveHistoryPayload,
  buildHistorySummary,
  historySummaryHasContent,
} from "@/lib/backtest-history";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strategy-1",
  totalReturn: 12.3,
  cagr: 7.8,
  buyAndHoldReturn: 3.4,
  maxDrawdown: -5.6,
  winRate: 52,
  profitFactor: 1.4,
  sharpe: 1.1,
  sortino: 1.2,
  kelly: 0.1,
  trades: 14,
  finalEquity: 11230000,
  initialCapital: 10000000,
  equity: [10000000, 11230000],
  dates: ["2025-01-01", "2025-12-31"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
};

const summary = {
  strategyName: "테스트 전략",
  universeName: "KOSPI",
  entryBlocks: ["MACD"],
  exitBlocks: ["RSI"],
};

describe("buildAutoSaveHistoryPayload", () => {
  it("cacheKey가 없으면 상세 result를 함께 저장해야 함", () => {
    const payload = buildAutoSaveHistoryPayload(baseResult, summary);
    expect(payload.result).toEqual(baseResult);
    expect(payload.cacheKey).toBeUndefined();
    expect(payload.isAutoSave).toBe(true);
  });

  it("cacheKey가 있어도 상세 result를 함께 보내 SOT 미생성 시 빈 기록을 방지한다", () => {
    // 회귀: 스트리밍 저장은 stream close 후 saveCachedResult를 비동기 실행하므로
    // 자동 저장 POST가 SOT 레코드보다 먼저 도달하면(또는 저장 실패 시) result를
    // 생략한 payload가 목록에 상세 결과 없는 카드를 만들었다. cacheKey가 있어도
    // result를 함께 보내면 POST 라우트가 기존 값을 우선 유지하므로 중복이 아니다.
    const payload = buildAutoSaveHistoryPayload(
      { ...baseResult, cacheKey: "cache-123" },
      summary
    );
    expect(payload.cacheKey).toBe("cache-123");
    expect(payload.result).toEqual({ ...baseResult, cacheKey: "cache-123" });
  });

  it("전략명이 있으면 전략명을 이름으로 사용한다", () => {
    expect(
      buildAutoSaveHistoryPayload(baseResult, summary, "코스피 골든크로스").strategyName
    ).toBe("테스트 전략");
  });

  it("전략명이 없으면 사용자 프롬프트를 이름으로 사용한다", () => {
    const unsavedSummary = { ...summary, strategyName: "" };
    expect(
      buildAutoSaveHistoryPayload(baseResult, unsavedSummary, "  코스피 골든크로스  ").strategyName
    ).toBe("코스피 골든크로스");
  });

  it("전략명·프롬프트 모두 없을 때만 기본 이름으로 폴백한다", () => {
    const unsavedSummary = { ...summary, strategyName: "" };
    expect(buildAutoSaveHistoryPayload(baseResult, unsavedSummary).strategyName).toBe("이름 없는 전략");
    expect(
      buildAutoSaveHistoryPayload(baseResult, unsavedSummary, "   ").strategyName
    ).toBe("이름 없는 전략");
  });

  it("프롬프트 원문을 스냅샷으로 함께 저장한다(trim, 빈 값은 undefined)", () => {
    expect(
      buildAutoSaveHistoryPayload(baseResult, summary, "  KOSPI 골든크로스 전략  ").prompt
    ).toBe("KOSPI 골든크로스 전략");
    expect(buildAutoSaveHistoryPayload(baseResult, summary, "   ").prompt).toBeUndefined();
    expect(buildAutoSaveHistoryPayload(baseResult, summary).prompt).toBeUndefined();
  });
});

describe("백테스트 기간·초기 자본의 저장·복원 (2026-08-18)", () => {
  // 저장된 전략·기록에서도 실행 조건이 정확히 보여야 한다 — 요약 DTO의 기간·자본 텍스트를
  // conditions(backtestPeriod/initialCapital)로 남기고, 그 전에 저장된 행은 실행 요청에서 되살린다.
  it("자동 저장 payload가 기간·초기 자본·리밸런싱을 conditions에 남긴다", () => {
    const payload = buildAutoSaveHistoryPayload(baseResult, {
      ...summary,
      positionText: "최대 12종목",
      rebalancingText: "매월 리밸런싱",
      riskText: "손절 -10%",
      backtestPeriodText: "3년",
      initialCapitalText: "10,000,000원",
    });
    expect(payload.conditions).toMatchObject({
      position: "최대 12종목",
      rebalancing: "매월 리밸런싱",
      risk: "손절 -10%",
      backtestPeriod: "3년",
      initialCapital: "10,000,000원",
    });
  });

  it("buildHistorySummary는 conditions의 기간·자본을 그대로 복원한다", () => {
    const restored = buildHistorySummary({
      conditions: {
        entry: { logic: "AND", names: ["MACD"] },
        exit: { logic: "AND", names: [] },
        backtestPeriod: "3년",
        initialCapital: "10,000,000원",
        rebalancing: "매월 리밸런싱",
      },
      universeName: "KOSPI",
    });
    expect(restored.backtestPeriodText).toBe("3년");
    expect(restored.initialCapitalText).toBe("10,000,000원");
    expect(restored.rebalancingText).toBe("매월 리밸런싱");
  });

  it("기간·자본이 없는 구버전 행은 결과의 실행 요청(executedRequest)에서 되살린다", () => {
    const restored = buildHistorySummary({
      conditions: { entry: { logic: "AND", names: ["MACD"] }, exit: { logic: "AND", names: [] } },
      universeName: "KOSPI",
      executedRequest: { period: "3y", risk: { init_cash: 10_000_000 }, entry: {}, exit: {} },
    });
    expect(restored.backtestPeriodText).toBe("3년");
    expect(restored.initialCapitalText).toBe("10,000,000원");
    // 직접 지정 창도 같은 경로
    const custom = buildHistorySummary({
      conditions: {},
      executedRequest: { period: "custom", startDate: "2020-01-01", endDate: "2023-01-01", risk: {} },
    });
    expect(custom.backtestPeriodText).toBe("3년 (2020-01-01 ~ 2023-01-01)");
    expect(custom.initialCapitalText).toBeUndefined();
  });

  it("conditions 값이 실행 요청보다 우선한다", () => {
    const restored = buildHistorySummary({
      conditions: { backtestPeriod: "5년", initialCapital: "50,000,000원" },
      executedRequest: { period: "3y", risk: { init_cash: 10_000_000 } },
    });
    expect(restored.backtestPeriodText).toBe("5년");
    expect(restored.initialCapitalText).toBe("50,000,000원");
  });
});

describe("buildHistorySummary", () => {
  it("표시용 names 스키마를 진입/청산/포지션/리스크 배지로 변환한다", () => {
    const summary = buildHistorySummary({
      conditions: {
        entry: { logic: "AND", names: ["MA 크로스"] },
        exit: { logic: "AND", names: ["MA 크로스", "손절 -8% 하락시 매도"] },
        position: "최대 10종목",
        risk: "손절 8%, 익절 30%",
      },
      universeName: "KOSPI",
      strategyName: "골드 크로스",
    });

    expect(summary.entryBlocks).toEqual(["MA 크로스"]);
    expect(summary.exitBlocks).toEqual(["MA 크로스", "손절 -8% 하락시 매도"]);
    expect(summary.blockNames).toEqual(["MA 크로스", "MA 크로스", "손절 -8% 하락시 매도"]);
    expect(summary.positionText).toBe("최대 10종목");
    expect(summary.riskText).toBe("손절 8%, 익절 30%");
    expect(historySummaryHasContent(summary)).toBe(true);
  });

  it("raw DSL conditions만(표시용 names 없음) 가진 행은 빈 요약 → SOT 미채택 판정", () => {
    const summary = buildHistorySummary({
      conditions: {
        entry: { conditions: [{ type: "indicator", id: "ma_crossover" }] },
        exit: { conditions: [{ type: "indicator", id: "ma_crossover" }] },
      },
      universeName: "KOSPI",
      strategyName: "골드 크로스",
    });

    expect(summary.entryBlocks).toEqual([]);
    expect(summary.exitBlocks).toEqual([]);
    expect(historySummaryHasContent(summary)).toBe(false);
  });

  it("레거시 평면 conditions(배열/{logic,names})도 진입 배지로 처리한다", () => {
    expect(buildHistorySummary({ conditions: ["MACD", "RSI"] }).entryBlocks).toEqual(["MACD", "RSI"]);
    expect(
      buildHistorySummary({ conditions: { logic: "OR", names: ["거래량 급증"] } }).entryBlocks
    ).toEqual(["거래량 급증"]);
  });
});
