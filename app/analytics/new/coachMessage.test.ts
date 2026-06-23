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

  it("묶어서 친근하게 안내한다 (손절·익절·청산 누락)", () => {
    expect(
      normalizeCoachMessage(
        JSON.stringify({
          is_valid: false,
          issues: [
            { category: "missing_field", field: "exit_rule", severity: "error", message: "청산 조건이 정의되어 있지 않습니다." },
            { category: "missing_field", field: "stop_loss_pct", severity: "warning", message: "손절 조건이 정의되어 있지 않습니다." },
            { category: "missing_field", field: "take_profit_pct", severity: "warning", message: "익절 조건이 정의되어 있지 않습니다." },
          ],
        }),
        "fallback"
      )
    ).toBe(
      "전략이 아직 완전히 구성되지는 않았습니다.\n\n" +
        "손절, 익절, 청산 조건이 비어 있지만 현재 상태로도 백테스트를 실행할 수 있습니다.\n\n" +
        "먼저 결과를 확인해 보고, 필요하면 나중에 조건을 추가해 보세요.\n\n" +
        "백테스트를 시작할까요?"
    );
  });

  it("누락 외 실제 이슈(예: 잘못된 파라미터)는 사실대로 함께 안내한다", () => {
    expect(
      normalizeCoachMessage(
        JSON.stringify({
          is_valid: false,
          issues: [
            { category: "missing_field", field: "exit_rule", severity: "error", message: "청산 조건이 정의되어 있지 않습니다." },
            { category: "invalid_parameter", field: "period", severity: "error", message: "RSI 기간은 1 이상의 값이어야 합니다." },
          ],
        }),
        "fallback"
      )
    ).toBe(
      "전략이 아직 완전히 구성되지는 않았습니다.\n\n" +
        "청산 조건이 비어 있지만 현재 상태로도 백테스트를 실행할 수 있습니다.\n\n" +
        "RSI 기간은 1 이상의 값이어야 합니다.\n\n" +
        "먼저 결과를 확인해 보고, 필요하면 나중에 조건을 추가해 보세요.\n\n" +
        "백테스트를 시작할까요?"
    );
  });

  it("누락 필드가 없는 경고만 있을 때도 친근하게 안내한다", () => {
    expect(
      normalizeCoachMessage(
        '{"is_valid":true,"issues":[{"severity":"warning","category":"universe_risk","message":"조건으로 인해 대상 종목이 존재하지 않을 수 있습니다."}]}',
        "fallback"
      )
    ).toBe(
      "전략이 아직 완전히 구성되지는 않았습니다.\n\n" +
        "조건으로 인해 대상 종목이 존재하지 않을 수 있습니다.\n\n" +
        "현재 상태로도 백테스트를 실행할 수 있습니다.\n\n" +
        "먼저 결과를 확인해 보고, 필요하면 나중에 조건을 추가해 보세요.\n\n" +
        "백테스트를 시작할까요?"
    );
  });

  it("falls back when the value is empty or not text", () => {
    expect(normalizeCoachMessage("", "fallback")).toBe("fallback");
    expect(normalizeCoachMessage(undefined, "fallback")).toBe("fallback");
  });
});
