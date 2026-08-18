// 응답 조립기 계약(FR-SA-017 ②). 분기마다 손으로 메시지를 조립하던 구조에서 나온 사고를
// 구조적으로 불가능하게 만드는 것이 이 파일의 목적이다 — 아래 단언이 깨지면 그 사고가 돌아온다.
import { describe, expect, it } from "vitest";

import { buildTurnMessage, type OpenClarification, type TurnPresentation } from "./turnMessage";
import type { ConversationDecision } from "./conversationDecision";

const presentation: TurnPresentation = {
  summaryItems: [{ label: "유니버스", value: "KOSPI" }] as TurnPresentation["summaryItems"],
  progressItems: [{ label: "리밸런싱", complete: false }] as TurnPresentation["progressItems"],
};

const askDecision: ConversationDecision = {
  action: "ask_next_condition",
  speechAct: "ask",
  topic: "strategy",
  confidence: 1,
  reason: "active_strategy_next_condition",
  field: "rebalancing",
  message: "포트폴리오를 얼마나 자주 다시 구성할까요?",
  suggestions: ["매월 리밸런싱", "안 함"],
};

const greetingDecision: ConversationDecision = {
  action: "respond",
  speechAct: "unknown",
  topic: "general",
  confidence: 1,
  reason: "classified_greeting",
  message: "안녕하세요. 어떤 투자 아이디어를 가지고 계신가요?",
  preservesOpenQuestion: true,
};

const openClarification: OpenClarification = {
  parsed: { description: "전략" },
  clarification: "리밸런싱 주기는 어떻게 할까요?",
  clarificationSuggestions: ["매월 리밸런싱"],
  builderPresentation: presentation,
};

describe("buildTurnMessage", () => {
  it("상태가 정한 되묻기는 질문과 선택지가 같은 결정에서 나온다", () => {
    const message = buildTurnMessage({
      decision: askDecision,
      presentation,
      parsed: { description: "전략" },
    });
    expect(message.clarification).toBe(askDecision.message);
    expect(message.clarificationSuggestions).toEqual(askDecision.suggestions);
    // 되묻기 선택지는 결정론 귀속 채널로만 나간다 — infoSuggestions로 새면 칩 클릭이
    // 새 발화로 재전송돼 백엔드 왕복이 생기고 값 결속이 끊긴다.
    expect(message.infoSuggestions).toBeUndefined();
    expect(message.builderPresentation).toBe(presentation);
    // 어떤 슬롯을 묻는지도 함께 싣는다 — 렌더가 선택지 닫힘 여부를 이 값으로 판정한다
    // (질문 문구는 사용자 친화 문구로 치환되므로 근거가 못 된다).
    expect(message.clarificationField).toBe(askDecision.field);
  });

  it("되묻기 레인의 질문(respond+opensClarification)도 상태 되묻기와 같은 카드로 나간다", () => {
    // 2026-08-17 사용자 신고: '손절 바꿔줘'의 되묻기가 박스가 아니라 맨 텍스트+칩으로 보였다.
    // respond 액션이라 infoText 채널로 나간 것 — 같은 성격의 질문은 같은 카드여야 한다.
    const modifyAsk: ConversationDecision = {
      action: "respond",
      speechAct: "modify",
      topic: "risk",
      confidence: 1,
      reason: "missing_stop_loss_value",
      message: "손절 기준을 몇 %로 변경할까요?",
      suggestions: ["손절을 -5%로 변경", "직접 입력"],
      opensClarification: true,
    };
    const message = buildTurnMessage({
      decision: modifyAsk,
      presentation,
      askPresentation: presentation,
      parsed: { description: "전략" },
    });
    expect(message.clarification).toBe(modifyAsk.message);
    expect(message.clarificationSuggestions).toEqual(modifyAsk.suggestions);
    expect(message.infoText).toBeUndefined();
    expect(message.infoSuggestions).toBeUndefined();
    expect(message.builderPresentation).toBe(presentation);
    expect(message.parsed).toEqual({ description: "전략" });
  });

  it("되묻기 레인의 질문에는 열려 있던 되묻기를 되살리지 않는다 — 질문이 겹친다", () => {
    const message = buildTurnMessage({
      decision: {
        action: "respond",
        speechAct: "modify",
        topic: "risk",
        confidence: 1,
        reason: "missing_stop_loss_value",
        message: "손절 기준을 몇 %로 변경할까요?",
        suggestions: ["손절을 -5%로 변경"],
        opensClarification: true,
        preservesOpenQuestion: true,
      },
      openClarification,
    });
    expect(message.clarification).toBe("손절 기준을 몇 %로 변경할까요?");
    expect(message.clarificationSuggestions).toEqual(["손절을 -5%로 변경"]);
  });

  it("되묻기 렌더에 필요한 parsed를 함께 싣는다", () => {
    // clarification 블록은 msg.parsed가 없으면 그려지지 않는다.
    expect(buildTurnMessage({ decision: askDecision, parsed: { x: 1 } }).parsed).toEqual({ x: 1 });
  });

  it("안내 턴은 전략 카드를 항상 함께 낸다", () => {
    const message = buildTurnMessage({ decision: greetingDecision, presentation });
    expect(message.infoText).toBe(greetingDecision.message);
    expect(message.builderPresentation).toBe(presentation);
  });

  it("부가 발화는 열려 있던 되묻기를 그대로 다시 세운다", () => {
    const message = buildTurnMessage({
      decision: greetingDecision,
      presentation,
      openClarification,
    });
    expect(message.infoText).toBe(greetingDecision.message);
    expect(message.clarification).toBe(openClarification.clarification);
    expect(message.clarificationSuggestions).toEqual(openClarification.clarificationSuggestions);
    // 질문 당시의 카드를 우선한다.
    expect(message.builderPresentation).toBe(presentation);
  });

  it("스스로 질문을 던지는 턴에는 열린 되묻기를 되살리지 않는다 — 질문이 겹친다", () => {
    const message = buildTurnMessage({
      decision: { ...askDecision, preservesOpenQuestion: true },
      openClarification,
      parsed: { description: "전략" },
    });
    expect(message.clarification).toBe(askDecision.message);
  });

  it("보존 표시가 없는 턴은 되묻기를 되살리지 않는다", () => {
    const message = buildTurnMessage({
      decision: { ...greetingDecision, preservesOpenQuestion: undefined },
      openClarification,
    });
    expect(message.clarification).toBeUndefined();
  });

  it("네트워크로 받아온 답변 문구가 decision.message보다 우선한다", () => {
    const message = buildTurnMessage({
      decision: {
        action: "answer_general",
        speechAct: "ask",
        topic: "general",
        confidence: 1,
        reason: "classified_general_investment",
      },
      answerText: "PBR은 주가를 주당순자산으로 나눈 지표입니다.",
    });
    expect(message.infoText).toBe("PBR은 주가를 주당순자산으로 나눈 지표입니다.");
  });
});
