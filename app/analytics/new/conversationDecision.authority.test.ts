import { describe, expect, it } from "vitest";
import { decideConversationTurn, type ConversationContext } from "./conversationDecision";

const context: ConversationContext = {
  stage: "ready", hasBacktestRequest: true, hasCurrentStrategy: true,
  builderMode: false, lastCoachText: "백테스트를 진행할까요?", slots: { next: null },
};

describe("structured turn authority", () => {
  it("classifies a confirmation-looking utterance before interpreting it", () => {
    expect(decideConversationTurn("네 진행해", context).action).toBe("classify");
  });

  it("uses the LLM confirmation axis without matching user words", () => {
    expect(decideConversationTurn("이 문장은 규칙에 없는 표현", context,
      { intent: "STRATEGY_ADVICE", turnAction: "run_backtest" }).action).toBe("run_backtest");
  });

  it("does not execute when the classification also reports an update", () => {
    expect(decideConversationTurn("진행 전에 바꿔줘", context,
      { intent: "STRATEGY_ADVICE", turnAction: "run_backtest", workflowEffect: "UPDATE" }).action).toBe("parse_strategy");
  });

  it("does not infer follow-up meaning from words", () => {
    expect(decideConversationTurn("다음은 어떻게 해야 해?", context,
      { intent: "STRATEGY_ADVICE" }).action).toBe("parse_strategy");
  });

  it("keeps the regulatory response ahead of research routing", () => {
    const result = decideConversationTurn("연구 지표", { ...context, pendingResearchMetricPrompt: "이전 연구 목표" },
      { intent: "PERSONAL_ADVICE", suggestedReply: "개인 맞춤 조언은 제공하지 않아요." });
    expect(result.action).toBe("respond");
    expect(result.reason).toBe("classified_personal_advice");
  });

  it("does not recover an interpretation failure with research words", () => {
    const result = decideConversationTurn("샤프 최대화", context,
      { intent: "UNKNOWN", interpretationFailed: true });
    expect(result.action).toBe("respond");
  });
});
