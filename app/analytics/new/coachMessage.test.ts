import { describe, expect, it } from "vitest";
import { normalizeCoachMessage } from "./coachMessage";

describe("normalizeCoachMessage", () => {
  it("uses plain coach text as-is", () => {
    expect(normalizeCoachMessage("짧은 코칭 문장", "fallback")).toBe("짧은 코칭 문장");
  });

  it("extracts message from a JSON string response", () => {
    expect(
      normalizeCoachMessage(
        '{"message": "초보자분께 좋은 전략입니다."}',
        "fallback"
      )
    ).toBe("초보자분께 좋은 전략입니다.");
  });

  it("extracts message from a JSON code block response", () => {
    expect(
      normalizeCoachMessage(
        '```json\n{"message": "트레일링 스탑을 추가해 보세요."}\n```',
        "fallback"
      )
    ).toBe("트레일링 스탑을 추가해 보세요.");
  });

  it("falls back when the value is empty or not text", () => {
    expect(normalizeCoachMessage("", "fallback")).toBe("fallback");
    expect(normalizeCoachMessage(undefined, "fallback")).toBe("fallback");
  });
});
