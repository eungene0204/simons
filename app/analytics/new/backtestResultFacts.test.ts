// 결과 사실 블록 테스트 — LLM에 넘기는 유일한 수치 근거다.
//
// 가장 위험한 실패는 "없는 값을 0으로 채우는 것"이다. 거래가 아직 없는데 '총 거래
// 수: 0회'가 사실로 들어가면 LLM은 그걸 사실로 받아 설명한다.

import { describe, expect, it } from "vitest";

import { buildBacktestResultFacts } from "./backtestResultFacts";

const result = {
  totalReturn: 148.2,
  cagr: 19.7,
  buyAndHoldReturn: 92.4,
  maxDrawdown: -22.5,
  winRate: 54,
  profitFactor: 1.63,
  sharpe: 1.21,
  sortino: 1.84,
  trades: 88,
} as any;

describe("buildBacktestResultFacts", () => {
  it("결과가 없으면 null (사실 없이 답변 레인을 부르지 않는다)", () => {
    expect(buildBacktestResultFacts(null)).toBeNull();
  });

  it("수치를 한 줄씩 사람이 읽는 라벨로 적는다", () => {
    const facts = buildBacktestResultFacts(result)!;

    expect(facts).toContain("총 수익률: +148.2%");
    expect(facts).toContain("최대 낙폭(MDD): -22.5%");
    expect(facts).toContain("승률: 54.0%");
    expect(facts).toContain("샤프 지수: 1.21");
    expect(facts).toContain("총 거래 수: 88회");
  });

  it("값이 없는 지표는 줄을 만들지 않는다 — 0으로 채우면 거짓 사실이 된다", () => {
    const facts = buildBacktestResultFacts({
      ...result,
      profitFactor: null,
      volatility: undefined,
    })!;

    expect(facts).not.toContain("Profit Factor");
    expect(facts).not.toContain("변동성");
    // 있는 값은 그대로 남는다.
    expect(facts).toContain("샤프 지수: 1.21");
  });

  it("유한하지 않은 수도 줄을 만들지 않는다", () => {
    const facts = buildBacktestResultFacts({ ...result, sharpe: Infinity, sortino: NaN })!;

    expect(facts).not.toContain("샤프 지수");
    expect(facts).not.toContain("소르티노");
  });
});
