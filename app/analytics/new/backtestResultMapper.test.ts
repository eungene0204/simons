import { describe, expect, it } from "vitest";
import { mapRawBacktestResult } from "./backtestResultMapper";

describe("mapRawBacktestResult", () => {
  it("백엔드가 보낸 avgHoldingDays를 보존한다 (0일로 누락되지 않음)", () => {
    const raw = {
      symbols: ["005930"],
      totalReturn: 12.3,
      avgHoldingDays: 16,
      trades: 5,
      equity: [1000, 1100],
      signals: [],
    };

    const result = mapRawBacktestResult(raw, "test_exec");

    expect(result.avgHoldingDays).toBe(16);
  });

  it("avgHoldingDays가 없으면 0으로 기본값 처리한다", () => {
    const result = mapRawBacktestResult({ equity: [1000], signals: [] }, "test_exec");
    expect(result.avgHoldingDays).toBe(0);
  });

  it("감사 신규 통계(exposure/DD기간/기대값/회복계수)를 보존한다", () => {
    const raw = {
      equity: [1000, 1100],
      signals: [],
      exposure: 91.1,
      maxDrawdownDuration: 548,
      expectancy: 3.3,
      recoveryFactor: 2.05,
    };
    const result = mapRawBacktestResult(raw, "test_exec");
    expect(result.exposure).toBe(91.1);
    expect(result.maxDrawdownDuration).toBe(548);
    expect(result.expectancy).toBe(3.3);
    expect(result.recoveryFactor).toBe(2.05);
  });

  it("감사 신규 통계가 없으면 0으로 기본값 처리한다", () => {
    const result = mapRawBacktestResult({ equity: [1000], signals: [] }, "test_exec");
    expect(result.exposure).toBe(0);
    expect(result.maxDrawdownDuration).toBe(0);
    expect(result.expectancy).toBe(0);
    expect(result.recoveryFactor).toBe(0);
  });

  it("핵심 지표와 equity 경계값을 매핑한다", () => {
    const result = mapRawBacktestResult(
      { totalReturn: 5, equity: [1000, 900, 1200], signals: [] },
      "exec_1",
    );
    expect(result.executionId).toBe("exec_1");
    expect(result.totalReturn).toBe(5);
    expect(result.initialCapital).toBe(1000);
    expect(result.finalEquity).toBe(1200);
  });

  it("dedup용 cacheKey를 보존한다 (자동저장·명시저장 히스토리 중복 방지)", () => {
    const result = mapRawBacktestResult(
      { equity: [1000], signals: [] },
      "exec_1",
      "ckey-123",
    );
    expect(result.cacheKey).toBe("ckey-123");
  });

  it("meta 키가 없으면 raw.cacheKey로 폴백한다", () => {
    const result = mapRawBacktestResult(
      { equity: [1000], signals: [], cacheKey: "raw-key" },
      "exec_1",
    );
    expect(result.cacheKey).toBe("raw-key");
  });

  it("cacheKey가 전혀 없으면 undefined", () => {
    const result = mapRawBacktestResult({ equity: [1000], signals: [] }, "exec_1");
    expect(result.cacheKey).toBeUndefined();
  });
});

describe("mapRawBacktestResult — 분위 그룹 비교(FR-BT-060)", () => {
  it("quantileGroups payload를 보존한다 (누락 시 그룹 비교 섹션이 조용히 사라짐)", () => {
    const qg = {
      groups: [{ group: 1, label: "1그룹", pctRange: [0, 10], totalReturn: 1, cagr: 1, maxDrawdown: -1, sharpe: 0.5, winRate: 50, trades: 3, finalEquity: 1000, equity: [1000], dates: ["2024-01-02"] }],
      metricLabel: "PER(주가수익비율)",
      orderLabel: "PER(주가수익비율) 낮은 순",
      groupCount: 10,
      mainGroup: 1,
    };
    const result = mapRawBacktestResult(
      { equity: [1000], signals: [], quantileGroups: qg },
      "exec_1",
    );
    expect(result.quantileGroups).toEqual(qg);
  });

  it("quantileGroups가 없으면 undefined", () => {
    const result = mapRawBacktestResult({ equity: [1000], signals: [] }, "exec_1");
    expect(result.quantileGroups).toBeUndefined();
  });
});

describe("mapRawBacktestResult — 정의되지 않는 지표", () => {
  it("손익비 null(손실 0건 = ∞)을 0으로 뭉개지 않는다", () => {
    // 회귀: `raw.profitFactor ?? 0` 이던 시절 전승한 전략이 손익비 0(최악)으로 표시됐다
    const mapped = mapRawBacktestResult(
      { equity: [10_000_000, 12_000_000], profitFactor: null },
      "exec_1"
    );
    expect(mapped.profitFactor).toBeNull();
  });

  it("켈리 null(승·패 한쪽 표본 없음)을 0%로 채우지 않는다", () => {
    // 회귀: 백엔드가 kelly를 안 내려보내 프론트가 0으로 채웠고, 그 0이 AI 리포트
    // 프롬프트에 "켈리 기준: 0.00%"로 사실처럼 주입됐다
    const mapped = mapRawBacktestResult({ equity: [10_000_000], kelly: null }, "exec_2");
    expect(mapped.kelly).toBeNull();
  });

  it("값이 있으면 그대로 전달한다", () => {
    const mapped = mapRawBacktestResult(
      { equity: [10_000_000], profitFactor: 1.85, kelly: 6.2 },
      "exec_3"
    );
    expect(mapped.profitFactor).toBe(1.85);
    expect(mapped.kelly).toBe(6.2);
  });
});
