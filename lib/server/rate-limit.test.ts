import { afterEach, describe, expect, it } from "vitest";
import { __resetRateLimitForTests, consumeRateLimit } from "@/lib/server/rate-limit";

afterEach(() => {
  __resetRateLimitForTests();
});

describe("consumeRateLimit", () => {
  it("한도까지 허용하고 초과분은 거부한다", () => {
    const now = 1_000_000;
    expect(consumeRateLimit("k", 3, 60_000, now)).toBe(true);
    expect(consumeRateLimit("k", 3, 60_000, now + 1)).toBe(true);
    expect(consumeRateLimit("k", 3, 60_000, now + 2)).toBe(true);
    expect(consumeRateLimit("k", 3, 60_000, now + 3)).toBe(false);
  });

  it("윈도우가 지나면 카운터가 초기화된다", () => {
    const now = 1_000_000;
    expect(consumeRateLimit("k", 1, 60_000, now)).toBe(true);
    expect(consumeRateLimit("k", 1, 60_000, now + 59_999)).toBe(false);
    expect(consumeRateLimit("k", 1, 60_000, now + 60_000)).toBe(true);
  });

  it("키가 다르면 독립적으로 센다", () => {
    const now = 1_000_000;
    expect(consumeRateLimit("a", 1, 60_000, now)).toBe(true);
    expect(consumeRateLimit("b", 1, 60_000, now)).toBe(true);
    expect(consumeRateLimit("a", 1, 60_000, now + 1)).toBe(false);
  });
});
