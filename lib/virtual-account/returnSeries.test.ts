import { describe, expect, it } from "vitest";
import { buildReturnSeries, isReturnRange } from "./returnSeries";

describe("buildReturnSeries", () => {
  it("총 자산에서 총 납입액을 뺀 값을 납입액으로 나눈 수익률로 바꾸고 날짜순으로 정렬한다", () => {
    const points = buildReturnSeries([
      { date: "2026-10-29", totalValue: 98_000_000, totalContributed: 100_000_000 },
      { date: "2026-10-28", totalValue: 101_000_000, totalContributed: 100_000_000 },
    ]);

    expect(points).toEqual([
      { time: "2026-10-28", returnPct: 1 },
      { time: "2026-10-29", returnPct: -2 },
    ]);
  });

  it("적립식 납입이 늘어도 납입액을 수익으로 세지 않는다", () => {
    const points = buildReturnSeries([
      { date: "2026-10-28", totalValue: 1_000_000, totalContributed: 1_000_000 },
      { date: "2026-10-29", totalValue: 1_500_000, totalContributed: 1_500_000 },
    ]);

    expect(points.map((p) => p.returnPct)).toEqual([0, 0]);
  });

  it("오늘 값을 마지막 점으로 붙이고, 같은 날짜가 저장돼 있으면 오늘 값이 이긴다", () => {
    const points = buildReturnSeries(
      [
        { date: "2026-10-29", totalValue: 101, totalContributed: 100 },
        { date: "2026-10-30", totalValue: 102, totalContributed: 100 },
      ],
      { date: "2026-10-30", totalValue: 103, totalContributed: 100 }
    );

    expect(points).toEqual([
      { time: "2026-10-29", returnPct: 1 },
      { time: "2026-10-30", returnPct: 3 },
    ]);
  });

  it("납입액이 0 이하이거나 숫자가 아닌 점은 건너뛴다", () => {
    const points = buildReturnSeries([
      { date: "2026-10-27", totalValue: 100, totalContributed: 0 },
      { date: "2026-10-28", totalValue: Number.NaN, totalContributed: 100 },
      { date: "2026-10-29", totalValue: 110, totalContributed: 100 },
    ]);

    expect(points).toEqual([{ time: "2026-10-29", returnPct: 10 }]);
  });
});

describe("isReturnRange", () => {
  it("허용된 기간만 통과시킨다", () => {
    expect(["1m", "3m", "all"].every(isReturnRange)).toBe(true);
    expect(isReturnRange("1w")).toBe(false);
    expect(isReturnRange(null)).toBe(false);
  });
});
