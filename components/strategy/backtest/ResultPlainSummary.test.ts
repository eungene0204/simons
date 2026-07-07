import { describe, expect, it } from "vitest";

import { buildMonteCarloPlainSummary, buildWalkForwardPlainSummary } from "./ResultPlainSummary";

const walkForwardBase = {
  windows: [
    { oos_metrics: { cagr: 12.5 } },
    { oos_metrics: { cagr: -3.2 } },
    { oos_metrics: { cagr: 8.1 } },
  ],
  aggregate: { avg_oos_cagr: 5.8, avg_oos_maxDrawdown: -14.2 },
  walk_forward_efficiency: 0.72,
};

describe("buildWalkForwardPlainSummary", () => {
  it("구간 수·평균 수익·승패 구간 수·WFE·MDD를 문장으로 만든다", () => {
    const items = buildWalkForwardPlainSummary(walkForwardBase);
    const joined = items.join("\n");

    expect(joined).toContain("3개 구간으로 나눠");
    expect(joined).toContain("연평균 5.8%의 수익");
    expect(joined).toContain("3개 중 2개 구간에서 수익, 1개 구간에서 손실");
    expect(joined).toContain("약 72%가");
    expect(joined).toContain("평균 14.2%까지 하락");
    expect(joined).not.toContain("미래 수익은 보장되지 않습니다");
  });

  it("평균 CAGR이 음수면 손실 문장으로 표현한다", () => {
    const items = buildWalkForwardPlainSummary({
      ...walkForwardBase,
      aggregate: { ...walkForwardBase.aggregate, avg_oos_cagr: -4.5 },
    });
    expect(items.join("\n")).toContain("연평균 4.5%의 손실");
  });

  it("wfe_valid=false면 비율 대신 계산 불가 안내를 넣는다", () => {
    const items = buildWalkForwardPlainSummary({ ...walkForwardBase, wfe_valid: false });
    const joined = items.join("\n");
    expect(joined).toContain("계산할 수 없었습니다");
    expect(joined).not.toContain("약 72%");
  });

  it("WFE가 음수면 검증 구간 손실로 설명한다", () => {
    const items = buildWalkForwardPlainSummary({ ...walkForwardBase, walk_forward_efficiency: -0.3 });
    expect(items.join("\n")).toContain("WFE 음수");
  });

  it("aggregate가 비어 있어도 방법 설명은 유지한다", () => {
    const items = buildWalkForwardPlainSummary({
      windows: [],
      aggregate: {},
      walk_forward_efficiency: 0,
    });
    const joined = items.join("\n");
    expect(joined).toContain("0개 구간");
    expect(joined).not.toContain("미래 수익은 보장되지 않습니다");
    expect(joined).not.toContain("연평균");
  });
});

const monteCarloBase = {
  nIterations: 1000,
  mode: "returns" as const,
  cagr: { median: 0.082, p05: -0.031 },
  mdd: { p95: 0.264 },
  probPositiveCagr: 0.87,
  probMddOver30pct: 0.02,
};

describe("buildMonteCarloPlainSummary", () => {
  it("시나리오 수·중앙값·하위 5%·수익 비중·낙폭을 문장으로 만든다", () => {
    const items = buildMonteCarloPlainSummary(monteCarloBase);
    const joined = items.join("\n");

    expect(joined).toContain("1,000가지 시나리오");
    expect(joined).toContain("일별 수익률을 무작위로 다시 섞어");
    expect(joined).toContain("절반은 연평균 수익률(CAGR)이 8.2% 이상");
    expect(joined).toContain("하위 5%)에서는 연평균 수익률이 -3.1%");
    expect(joined).toContain("87.0%는 수익으로 끝났고, 13.0%는 손실");
    expect(joined).toContain("30% 넘게 하락한 시나리오는 2.0%");
    expect(joined).toContain("26.4%까지 하락");
    expect(joined).not.toContain("위 내용은 모두 과거 데이터 기반 시뮬레이션 결과이며, 미래 수익은 보장되지 않습니다.");
  });

  it("거래 재표본 모드면 거래 건수와 거래 도중 낙폭 미반영 안내를 넣는다", () => {
    const items = buildMonteCarloPlainSummary({ ...monteCarloBase, mode: "trades", tradeCount: 42 });
    const joined = items.join("\n");
    expect(joined).toContain("완결 거래 42건");
    expect(joined).toContain("거래 도중의 낙폭은 반영되지 않습니다");
  });
});
