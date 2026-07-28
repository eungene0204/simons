import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import { buildBuilderTurnPresentation } from "./builderProgressPresentation";

const themeParsed: ParsedSummary = {
  description: "모바일솔루션 관련주 투자 전략",
  universe: [],
  target_symbols: ["108860", "139670", "051160"],
  fundamental_filters: [],
  entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: null,
  initial_capital: null,
} as unknown as ParsedSummary;

describe("buildBuilderTurnPresentation 리밸런싱 표시 게이트", () => {
  it("다종목 지정(테마 유니버스)은 답하기 전까지 기본값 '설정 안 함'을 확정 표시하지 않는다", () => {
    // [회귀 2026-07-28 '모바일솔루션 관련주' 사고] 지정 종목이 있으면 리밸런싱을 '명시됨'으로
    // 간주해 질문 없이 요약 카드에 '리밸런싱: 설정 안 함'이 노출되던 버그.
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      prompt: "모바일솔루션 관련주 투자 전략",
    });
    expect(
      presentation.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toBeUndefined();
  });

  it("사용자가 답하면(안 함 포함) 그 결정을 표시한다", () => {
    const declined = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      prompt: "모바일솔루션 관련주 투자 전략\n리밸런싱 안 함",
    });
    expect(
      declined.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "설정 안 함" });

    const monthly = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, rebalancing_period: "monthly" } as ParsedSummary,
      prompt: "모바일솔루션 관련주 투자 전략\n매월 리밸런싱",
    });
    expect(
      monthly.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "매월" });
  });

  it("단독 종목(지정 1개)은 교체가 없어 기존대로 '설정 안 함'을 표시한다", () => {
    const single = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, target_symbols: ["005930"] } as ParsedSummary,
      prompt: "삼성전자 골든크로스 전략",
    });
    expect(
      single.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "설정 안 함" });
  });
});

describe("buildBuilderTurnPresentation 지정 종목 배분 표시", () => {
  it("다종목 지정은 '최대 보유 N종목' 대신 실행 배분(균등 투자)을 표시한다", () => {
    // [2026-07-28 '모바일솔루션 관련주' 카드-실행 불일치] 지정 종목 모드는 변환기가
    // max_positions=지정 종목 수로 덮어쓰므로(FR-STR-068 ①) 기본값 '최대 보유 10종목'은
    // 실행과 다른 정보였다 — 파싱 카드와 동일한 FR-STR-068 ⑧ 표기로 통일.
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      prompt: "모바일솔루션 관련주 투자 전략",
    });
    expect(
      presentation.summaryItems.find((item) => item.label === "최대 보유"),
    ).toBeUndefined();
    expect(
      presentation.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ value: "지정 종목 3개 균등 투자" });
    expect(
      presentation.progressItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ complete: true });
  });

  it("단독 종목(지정 1개)은 '단일 종목 집중 투자'를 표시한다", () => {
    const single = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, target_symbols: ["005930"] } as ParsedSummary,
      prompt: "삼성전자 골든크로스 전략",
    });
    expect(
      single.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ value: "단일 종목 집중 투자" });
  });

  it("유니버스 전략은 기존대로 명시된 최대 보유 종목 수를 표시한다", () => {
    const universe = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: {
        ...themeParsed,
        target_symbols: [],
        universe: ["KOSPI200"],
        max_positions: 5,
      } as ParsedSummary,
      prompt: "코스피200 골든크로스 전략, 최대 5종목",
    });
    expect(
      universe.summaryItems.find((item) => item.label === "최대 보유"),
    ).toMatchObject({ value: "5종목" });
    expect(
      universe.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toBeUndefined();
  });
});
