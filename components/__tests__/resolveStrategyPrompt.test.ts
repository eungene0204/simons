import { describe, expect, it } from "vitest";
import { resolveStrategyPrompt } from "@/lib/strategy-summary";

describe("resolveStrategyPrompt", () => {
  it("settings.description(파싱 보존 원문)를 우선한다", () => {
    expect(
      resolveStrategyPrompt(
        { description: "  KOSPI 골든크로스 매수 전략  " },
        "골드 크로스"
      )
    ).toBe("KOSPI 골든크로스 매수 전략");
  });

  it("settings.description가 없으면 Strategy.description으로 폴백한다", () => {
    expect(resolveStrategyPrompt({}, "  골드 크로스  ")).toBe("골드 크로스");
    expect(resolveStrategyPrompt(null, "골드 크로스")).toBe("골드 크로스");
  });

  it("둘 다 없으면 빈 문자열", () => {
    expect(resolveStrategyPrompt(null, null)).toBe("");
    expect(resolveStrategyPrompt({ description: "   " }, "")).toBe("");
  });
});
