import { describe, expect, it } from "vitest";
import { computeLimitConversion, computeSourceFunnel, DIRECT_SOURCE } from "@/lib/server/revenueFunnel";

const d = (s: string) => new Date(s);

describe("revenueFunnel — 한도 도달 → 14일 안 결제", () => {
  it("첫 도달 뒤 14일 안 결제만 전환으로 센다", () => {
    const hits = [
      { userId: 1, code: "PLAN_LIMIT_BACKTESTS", createdAt: d("2026-11-01T00:00:00Z") },
      { userId: 1, code: "PLAN_LIMIT_STRATEGIES", createdAt: d("2026-11-03T00:00:00Z") },
      { userId: 2, code: "PLAN_LIMIT_BACKTESTS", createdAt: d("2026-11-01T00:00:00Z") },
      { userId: 3, code: "PLAN_LIMIT_BACKTESTS", createdAt: d("2026-11-10T00:00:00Z") },
    ];
    const paid = [
      { userId: 1, createdAt: d("2026-11-05T00:00:00Z") }, // 4일 뒤 → 전환
      { userId: 2, createdAt: d("2026-11-20T00:00:00Z") }, // 19일 뒤 → 전환 아님
      { userId: 3, createdAt: d("2026-11-09T00:00:00Z") }, // 도달 전 결제 → 전환 아님
    ];
    const result = computeLimitConversion(hits, paid);
    expect(result.users).toBe(3);
    expect(result.converted).toBe(1);
    expect(result.byCode).toEqual({ PLAN_LIMIT_BACKTESTS: 3, PLAN_LIMIT_STRATEGIES: 1 });
  });
});

describe("revenueFunnel — 가입 유입 경로", () => {
  it("경로별 가입·백테스트·결제를 세고, 경로 없는 가입은 (direct)로 묶는다", () => {
    const rows = computeSourceFunnel(
      [
        { id: 1, signupUtmSource: "x", backtestRunTotal: 3 },
        { id: 2, signupUtmSource: "x", backtestRunTotal: 0 },
        { id: 3, signupUtmSource: null, backtestRunTotal: 1 },
        { id: 4, signupUtmSource: "naver_blog", backtestRunTotal: 2 },
      ],
      new Set([1, 4])
    );
    expect(rows).toEqual([
      { source: "x", signups: 2, backtested: 1, paid: 1 },
      { source: DIRECT_SOURCE, signups: 1, backtested: 1, paid: 0 },
      { source: "naver_blog", signups: 1, backtested: 1, paid: 1 },
    ]);
  });
});
