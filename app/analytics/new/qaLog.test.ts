import { describe, it, expect } from "vitest";
import {
  answerKindOf,
  answerTextOf,
  collectQaTurns,
  selectLoggableQaTurns,
  type QaChatMessage,
} from "./qaLog";

const user = (content: string, chipAnswer = false): QaChatMessage => ({
  role: "user",
  content,
  ...(chipAnswer ? { chipAnswer: true } : {}),
});

describe("answerTextOf", () => {
  it("한 메시지가 띄운 블록을 그린 순서대로 잇는다", () => {
    const text = answerTextOf({
      role: "assistant",
      notices: ["초기 자금을 1,000만 원으로 맞췄어요"],
      parsed: { universe: "KOSPI200" },
      clarification: "손절 기준을 정해 주세요",
      clarificationSuggestions: ["5%", "10%"],
    });

    expect(text).toBe(
      [
        "안내: 초기 자금을 1,000만 원으로 맞췄어요",
        "[전략 요약 카드]",
        "손절 기준을 정해 주세요",
        "선택지: 5% / 10%",
      ].join("\n"),
    );
  });

  it("오류 메시지도 답변으로 남긴다", () => {
    expect(answerTextOf({ role: "assistant", error: "백테스트 오류" })).toBe(
      "오류: 백테스트 오류",
    );
  });

  it("빈 메시지는 빈 문자열이다", () => {
    expect(answerTextOf({ role: "assistant", isLoading: true })).toBe("");
  });
});

describe("answerKindOf", () => {
  it("사용자가 응답해야 하는 블록이 우선한다", () => {
    expect(
      answerKindOf({ role: "assistant", parsed: {}, clarification: "몇 종목?" }),
    ).toBe("clarification");
    expect(answerKindOf({ role: "assistant", parsed: {} })).toBe("strategy");
    expect(answerKindOf({ role: "assistant", coachText: "설명" })).toBe("coach");
    expect(answerKindOf({ role: "assistant", infoText: "안내" })).toBe("info");
    expect(answerKindOf({ role: "assistant" })).toBe("none");
  });
});

describe("collectQaTurns", () => {
  it("사용자 발화 하나와 그 뒤 응답 전부를 한 턴으로 묶는다", () => {
    const turns = collectQaTurns([
      user("RSI 30 이하 매수 전략 만들어줘"),
      { role: "assistant", parsed: { universe: "KOSPI" } },
      { role: "assistant", clarification: "몇 종목을 담을까요?" },
      user("10종목", true),
      { role: "assistant", coachText: "10종목으로 맞췄어요" },
    ]);

    expect(turns).toHaveLength(2);
    expect(turns[0]).toMatchObject({
      turnIndex: 0,
      question: "RSI 30 이하 매수 전략 만들어줘",
      chipAnswer: false,
      answerKind: "clarification",
      pending: false,
    });
    expect(turns[0].answer).toBe("[전략 요약 카드]\n\n몇 종목을 담을까요?");
    expect(turns[1]).toMatchObject({
      turnIndex: 1,
      question: "10종목",
      chipAnswer: true,
      answerKind: "coach",
    });
  });

  it("로딩 자리표시자가 남아 있는 턴은 pending이다", () => {
    const turns = collectQaTurns([
      user("코스피 대형주 모멘텀"),
      { role: "assistant", isLoading: true },
    ]);

    expect(turns[0].pending).toBe(true);
    expect(turns[0].answer).toBe("");
  });

  it("사용자 발화 없이 시작된 안내는 턴이 아니다", () => {
    expect(collectQaTurns([{ role: "assistant", infoText: "환영합니다" }])).toEqual([]);
  });
});

describe("selectLoggableQaTurns", () => {
  const conversation: QaChatMessage[] = [
    user("첫 질문"),
    { role: "assistant", coachText: "첫 답변" },
    user("둘째 질문"),
    { role: "assistant", coachText: "둘째 답변" },
  ];

  it("아직 보내지 않은 턴만 고른다", () => {
    expect(selectLoggableQaTurns(conversation, 0).map((t) => t.turnIndex)).toEqual([0, 1]);
    expect(selectLoggableQaTurns(conversation, 1).map((t) => t.turnIndex)).toEqual([1]);
    expect(selectLoggableQaTurns(conversation, 2)).toEqual([]);
  });

  it("응답이 끝나지 않은 턴에서 멈춘다 — 건너뛰면 그 턴이 영영 기록되지 않는다", () => {
    const inFlight: QaChatMessage[] = [
      user("첫 질문"),
      { role: "assistant", isLoading: true },
      user("둘째 질문"),
      { role: "assistant", coachText: "둘째 답변" },
    ];

    expect(selectLoggableQaTurns(inFlight, 0)).toEqual([]);
  });

  it("답변이 아직 없는 마지막 턴은 보내지 않는다", () => {
    const justAsked: QaChatMessage[] = [...conversation, user("셋째 질문")];

    expect(selectLoggableQaTurns(justAsked, 2)).toEqual([]);
  });
});
