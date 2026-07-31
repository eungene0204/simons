import { describe, expect, it } from "vitest";

import { selectClassifierHistory } from "./chatHistory";

// 실제 사고 재현 맥락: 직전 답변이 전략 예시를 보여준 뒤 "다른 예는 없어?"라고 물으면
// 분류 LLM이 문장만 보고 OFF_TOPIC으로 오판했다 — 최근 턴을 함께 보내 맥락으로 판단하게 한다.
describe("selectClassifierHistory", () => {
  it("사용자·assistant 텍스트를 role과 함께 뽑는다", () => {
    const history = selectClassifierHistory([
      { role: "user", content: "삼성전자 지금 사도 될까?" },
      { role: "assistant", infoText: "종목 추천은 제공하지 않아요. 예를 들어 RSI 전략…" },
    ]);
    expect(history).toEqual([
      { role: "user", text: "삼성전자 지금 사도 될까?" },
      { role: "assistant", text: "종목 추천은 제공하지 않아요. 예를 들어 RSI 전략…" },
    ]);
  });

  it("로딩 자리표시자와 빈 메시지는 제외한다", () => {
    const history = selectClassifierHistory([
      { role: "user", content: "안녕" },
      { role: "assistant", isLoading: true },
      { role: "assistant", infoText: "   " },
      { role: "assistant" },
    ]);
    expect(history).toEqual([{ role: "user", text: "안녕" }]);
  });

  it("assistant는 infoText → coachText → clarification 순으로 고른다", () => {
    expect(
      selectClassifierHistory([{ role: "assistant", coachText: "코치 답변" }])
    ).toEqual([{ role: "assistant", text: "코치 답변" }]);
    expect(
      selectClassifierHistory([{ role: "assistant", clarification: "되묻기" }])
    ).toEqual([{ role: "assistant", text: "되묻기" }]);
  });

  it("최근 턴만 남기고 긴 텍스트는 자른다", () => {
    const messages = Array.from({ length: 10 }, (_, i) => ({
      role: "user",
      content: `turn-${i}`,
    }));
    const history = selectClassifierHistory(messages);
    expect(history).toHaveLength(6);
    expect(history[0].text).toBe("turn-4");
    expect(history.at(-1)?.text).toBe("turn-9");

    const long = selectClassifierHistory([{ role: "user", content: "가".repeat(900) }]);
    expect(long[0].text).toHaveLength(500);
  });
});

describe("열린 되묻기가 분류 맥락에서 사라지지 않는다", () => {
  it("안내문과 되묻기가 함께 실린 메시지는 둘 다 맥락에 넣는다", () => {
    // FR-SA-015 이후 한 메시지가 안내문+되묻기를 함께 싣는다. 앞의 것만 고르면
    // 우리가 방금 던진 질문이 맥락에서 사라져, 그 답("아니야")이 인사로 오분류된다.
    const history = selectClassifierHistory([
      { role: "user", content: "어떻게 하지?" },
      {
        role: "assistant",
        infoText: "안녕하세요. 오늘은 어떤 전략을 연구해 볼까요?",
        clarification: "어떻게 하지?라는 표현이 무엇을 의미하는지 구체적으로 말씀해 주세요.",
      },
    ]);
    const assistantTurn = history[history.length - 1];
    expect(assistantTurn.text).toContain("안녕하세요");
    expect(assistantTurn.text).toContain("구체적으로 말씀해 주세요");
  });
});
