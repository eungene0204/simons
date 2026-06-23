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

  it("renders a valid strategy result without exposing JSON", () => {
    expect(
      normalizeCoachMessage('{"is_valid":true,"issues":[]}', "fallback")
    ).toBe("전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다.");
  });

  it("renders only factual validation issue messages", () => {
    expect(
      normalizeCoachMessage(
        JSON.stringify({
          is_valid: false,
          issues: [
            { message: "청산 조건이 정의되어 있지 않습니다." },
            { message: "RSI 기간은 1 이상의 값이어야 합니다." },
          ],
        }),
        "fallback"
      )
    ).toBe(
      "청산 조건이 정의되어 있지 않습니다.\nRSI 기간은 1 이상의 값이어야 합니다.\n\n현재 조건으로도 백테스트를 진행 할 수 있습니다. 진행 할까요?"
    );
  });

  it("renders warning messages even when execution is valid", () => {
    expect(
      normalizeCoachMessage(
        '{"is_valid":true,"issues":[{"severity":"warning","message":"조건으로 인해 대상 종목이 존재하지 않을 수 있습니다."}]}',
        "fallback"
      )
    ).toBe(
      "조건으로 인해 대상 종목이 존재하지 않을 수 있습니다.\n\n현재 조건으로도 백테스트를 진행 할 수 있습니다. 진행 할까요?"
    );
  });

  it("falls back when the value is empty or not text", () => {
    expect(normalizeCoachMessage("", "fallback")).toBe("fallback");
    expect(normalizeCoachMessage(undefined, "fallback")).toBe("fallback");
  });
});
