// @ts-nocheck
import { describe, expect, it } from "vitest";
import { cumulativePath, fanCheckpoints } from "./monteCarloFan";
import { runMonteCarloSimulation } from "./OptimizationPage";

function buildResult(length: number) {
  let value = 10_000_000;
  const equity = Array.from({ length }, (_, index) => {
    value *= index % 7 === 0 ? 0.99 : 1.004;
    return value;
  });
  return { equity, initialCapital: 10_000_000 };
}

describe("fanCheckpoints", () => {
  it("짧은 경로는 모든 걸음을, 긴 경로는 시작·끝을 포함해 고르게 덜어 낸다", () => {
    expect(fanCheckpoints(5)).toEqual([0, 1, 2, 3, 4, 5]);
    const long = fanCheckpoints(1234);
    expect(long[0]).toBe(0);
    expect(long[long.length - 1]).toBe(1234);
    expect(long.length).toBeLessThanOrEqual(101);
  });
});

describe("몬테카를로 경로 분포", () => {
  it("체크포인트마다 5 ≤ 25 ≤ 50 ≤ 75 ≤ 95 백분위 순서를 지키고 시작은 1×다", async () => {
    const result = await runMonteCarloSimulation(buildResult(400), { iterations: 300, blockSize: 5, seed: 3, mode: "returns" });
    const fan = result.fan;
    expect(fan.stepUnit).toBe("day");
    expect(fan.p50[0]).toBe(1);
    for (let i = 0; i < fan.steps.length; i += 1) {
      expect(fan.p05[i]).toBeLessThanOrEqual(fan.p25[i]);
      expect(fan.p25[i]).toBeLessThanOrEqual(fan.p50[i]);
      expect(fan.p50[i]).toBeLessThanOrEqual(fan.p75[i]);
      expect(fan.p75[i]).toBeLessThanOrEqual(fan.p95[i]);
    }
    expect(fan.samples.length).toBeGreaterThan(0);
    expect(fan.samples[0]).toHaveLength(fan.steps.length);
  });

  it("마지막 체크포인트의 경로 백분위는 CAGR 분포와 같은 순서다(분포와 경로가 같은 시나리오에서 나온다)", async () => {
    const result = await runMonteCarloSimulation(buildResult(400), { iterations: 400, blockSize: 1, seed: 11, mode: "returns" });
    const last = result.fan.steps.length - 1;
    // 같은 기간이라 최종 배수는 CAGR의 단조 함수 — 중앙값끼리 같은 시나리오 위치를 가리킨다.
    expect(result.fan.p50[last]).toBeGreaterThan(result.fan.p05[last]);
    expect(Math.sign(result.cagr.median)).toBe(Math.sign(result.fan.p50[last] - 1));
  });

  it("원래 순서 경로는 수익률을 순서대로 곱한 값이다", () => {
    expect(cumulativePath([0.1, -0.5], (r) => 1 + r)).toEqual([1, 1.1, 0.55]);
  });
});
