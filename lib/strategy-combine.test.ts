import { describe, expect, it } from "vitest";

import { combineStats, combineStrategies } from "./strategy-combine";

function dates(n: number, start = "2024-01-01") {
  const out: string[] = [];
  const d = new Date(start);
  while (out.length < n) {
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

describe("combineStrategies", () => {
  it("두 전략을 50/50으로 섞으면 리밸런싱 없이 각 곡선의 평균이 된다", () => {
    const ds = dates(10);
    const a = ds.map((_, i) => 100 * (1 + 0.01 * i));
    const b = ds.map(() => 100);
    const r = combineStrategies(
      [
        { id: "a", name: "A", dates: ds, equity: a, weight: 50 },
        { id: "b", name: "B", dates: ds, equity: b, weight: 50 },
      ],
      "none",
    );
    expect(r.dates).toEqual(ds);
    expect(r.combined[9]).toBeCloseTo((a[9] / a[0] + 1) / 2, 10);
    expect(r.components[0].weight).toBe(50);
    expect(r.correlation[0][0]).toBeCloseTo(1, 10);
  });

  it("월간 리밸런싱은 달이 바뀌는 첫 거래일에 목표 비중으로 되돌린다", () => {
    const ds = dates(45);
    const a = ds.map((_, i) => 100 * 1.02 ** i);
    const b = ds.map(() => 100);
    const none = combineStrategies(
      [
        { id: "a", name: "A", dates: ds, equity: a, weight: 50 },
        { id: "b", name: "B", dates: ds, equity: b, weight: 50 },
      ],
      "none",
    );
    const monthly = combineStrategies(
      [
        { id: "a", name: "A", dates: ds, equity: a, weight: 50 },
        { id: "b", name: "B", dates: ds, equity: b, weight: 50 },
      ],
      "monthly",
    );
    expect(monthly.rebalanceCount).toBeGreaterThanOrEqual(1);
    // 오르는 A를 되팔아 B에 옮기므로 최종 자산은 드리프트보다 작다.
    expect(monthly.combined[44]).toBeLessThan(none.combined[44]);
  });

  it("공통 거래일만 쓰고 비중은 정규화한다", () => {
    const ds = dates(20);
    const r = combineStrategies(
      [
        { id: "a", name: "A", dates: ds, equity: ds.map(() => 100), weight: 30 },
        { id: "b", name: "B", dates: ds.slice(5), equity: ds.slice(5).map(() => 200), weight: 10 },
      ],
      "none",
    );
    expect(r.dates).toEqual(ds.slice(5));
    expect(r.components.map((c) => c.weight)).toEqual([75, 25]);
    expect(r.combined.every((v) => Math.abs(v - 1) < 1e-12)).toBe(true);
  });

  it("통계는 246거래일 연환산·초기값 기준 낙폭이다", () => {
    const ds = dates(4);
    const s = combineStats([1, 0.9, 0.95, 1.1], ds);
    expect(s.totalReturn).toBeCloseTo(10, 8);
    expect(s.maxDrawdown).toBeCloseTo(-10, 8);
    expect(s.volatility).toBeGreaterThan(0);
    expect(s.calmar).not.toBeNull();
  });

  it("공통 거래일이 없으면 오류", () => {
    expect(() =>
      combineStrategies(
        [
          { id: "a", name: "A", dates: dates(5), equity: [1, 1, 1, 1, 1], weight: 1 },
          { id: "b", name: "B", dates: dates(5, "2025-01-01"), equity: [1, 1, 1, 1, 1], weight: 1 },
        ],
        "none",
      ),
    ).toThrow();
  });
});
