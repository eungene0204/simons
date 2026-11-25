import { describe, expect, it } from "vitest";

import { dailyExampleIndex, localDateKey } from "./dailyExample";

describe("dailyExample", () => {
  it("기기 날짜를 YYYY-MM-DD로 만든다", () => {
    expect(localDateKey(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });

  it("같은 날짜는 항상 같은 예시를, 범위 안에서 고른다", () => {
    const first = dailyExampleIndex(81, "2026-11-25");
    expect(dailyExampleIndex(81, "2026-11-25")).toBe(first);
    expect(first).toBeGreaterThanOrEqual(0);
    expect(first).toBeLessThan(81);
  });

  it("날짜가 바뀌면 고르는 예시도 돌아간다(한 달 동안 여러 예시가 나온다)", () => {
    const picks = new Set(
      Array.from({ length: 30 }, (_, i) => dailyExampleIndex(81, localDateKey(new Date(2026, 10, i + 1)))),
    );
    expect(picks.size).toBeGreaterThan(10);
  });

  it("예시가 없으면 -1", () => {
    expect(dailyExampleIndex(0, "2026-11-25")).toBe(-1);
  });
});
