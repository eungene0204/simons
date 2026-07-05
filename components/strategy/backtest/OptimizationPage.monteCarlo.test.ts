// @ts-nocheck
import { describe, expect, it } from "vitest";

import {
  buildMonteCarloHistogram,
  runMonteCarloSimulation,
} from "./OptimizationPage";

function buildResult(length: number) {
  let value = 10_000_000;
  const equity = Array.from({ length }, (_, index) => {
    value *= index % 7 === 0 ? 0.99 : 1.004;
    return value;
  });
  return { equity, initialCapital: 10_000_000 };
}

const settings = { iterations: 200, blockSize: 21, seed: 42 };

describe("runMonteCarloSimulation", () => {
  it("equity 데이터가 부족하면 에러를 반환한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(30), settings);
    expect(result.status).toBe("error");
    expect(result.message).toContain("최소");
  });

  it("분포 요약에 min/max·사분위·표준편차를 모두 제공한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");

    for (const summary of [result.cagr, result.sharpe, result.mdd]) {
      expect(summary.min).toBeLessThanOrEqual(summary.p05);
      expect(summary.p05).toBeLessThanOrEqual(summary.p25);
      expect(summary.p25).toBeLessThanOrEqual(summary.median);
      expect(summary.median).toBeLessThanOrEqual(summary.p75);
      expect(summary.p75).toBeLessThanOrEqual(summary.p95);
      expect(summary.p95).toBeLessThanOrEqual(summary.max);
      expect(summary.std).toBeGreaterThanOrEqual(0);
    }
    // MDD는 항상 0 이상
    expect(result.mdd.min).toBeGreaterThanOrEqual(0);
    expect(result.probPositiveCagr).toBeGreaterThanOrEqual(0);
    expect(result.probPositiveCagr).toBeLessThanOrEqual(1);
    expect(result.probMddOver30pct).toBeGreaterThanOrEqual(0);
    expect(result.probMddOver30pct).toBeLessThanOrEqual(1);
  });

  it("히스토그램 빈도의 합은 반복 횟수와 같다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");

    const cagrTotal = result.cagrHistogram.reduce((sum, bin) => sum + bin.count, 0);
    const mddTotal = result.mddHistogram.reduce((sum, bin) => sum + bin.count, 0);
    expect(cagrTotal).toBe(result.nIterations);
    expect(mddTotal).toBe(result.nIterations);
  });

  it("blockSize 1(일별 독립 재표본)도 동작한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), {
      ...settings,
      blockSize: 1,
    });
    expect(result.status).toBe("ok");
    expect(result.blockSize).toBe(1);
  });

  it("같은 seed는 같은 분포를 재현한다", async () => {
    const first = await runMonteCarloSimulation(buildResult(300), settings);
    const second = await runMonteCarloSimulation(buildResult(300), settings);
    expect(first.status).toBe("ok");
    expect(second.status).toBe("ok");
    expect(first.cagr).toEqual(second.cagr);
    expect(first.mdd).toEqual(second.mdd);
  });

  it("취소 콜백이 true를 반환하면 중단한다", async () => {
    const result = await runMonteCarloSimulation(
      buildResult(300),
      { ...settings, iterations: 2000 },
      undefined,
      () => true
    );
    expect(result.status).toBe("cancelled");
  });

  it("진행률 콜백은 0~1 범위로 증가하며 마지막에 1을 보고한다", async () => {
    const reported: number[] = [];
    const result = await runMonteCarloSimulation(
      buildResult(300),
      { ...settings, iterations: 1000 },
      (ratio) => reported.push(ratio)
    );
    expect(result.status).toBe("ok");
    expect(reported.length).toBeGreaterThan(0);
    expect(reported[reported.length - 1]).toBe(1);
    for (let i = 1; i < reported.length; i += 1) {
      expect(reported[i]).toBeGreaterThanOrEqual(reported[i - 1]);
    }
  });
});

describe("buildMonteCarloHistogram", () => {
  it("빈 배열이면 빈 히스토그램을 반환한다", () => {
    expect(buildMonteCarloHistogram([])).toEqual([]);
  });

  it("모든 값이 같으면 단일 구간으로 묶는다", () => {
    expect(buildMonteCarloHistogram([0.1, 0.1, 0.1])).toEqual([
      { x0: 0.1, x1: 0.1, count: 3 },
    ]);
  });

  it("구간 수와 총 빈도를 보존한다", () => {
    const values = Array.from({ length: 500 }, (_, index) => Math.sin(index) * 0.2);
    const bins = buildMonteCarloHistogram(values, 24);
    expect(bins).toHaveLength(24);
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(500);
    expect(bins[0].x0).toBeCloseTo(Math.min(...values));
    expect(bins[bins.length - 1].x1).toBeCloseTo(Math.max(...values));
  });
});
