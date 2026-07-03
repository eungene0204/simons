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
