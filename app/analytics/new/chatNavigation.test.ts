import { afterEach, describe, expect, it, vi } from "vitest";

import {
  beginStrategyChatNavigation,
  selectPersistableChatMessages,
  shouldBeginStrategyChatNavigation,
  shouldShowChatInputBox,
} from "./chatNavigation";

describe("strategy chat navigation", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores the prompt and pushes the chat route once", () => {
    const navigate = vi.fn();

    beginStrategyChatNavigation("테스트 전략", navigate, sessionStorage);

    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(
      "테스트 전략"
    );
    expect(navigate).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledWith("/analytics?chat=1");
  });

  it("starts route navigation for the first message regardless of prompt source", () => {
    expect(shouldBeginStrategyChatNavigation(false, 0)).toBe(true);
    expect(shouldBeginStrategyChatNavigation(true, 0)).toBe(false);
    expect(shouldBeginStrategyChatNavigation(false, 1)).toBe(false);
  });
});

describe("selectPersistableChatMessages", () => {
  it("clears transient loading flags so restored messages don't show forever-loading state", () => {
    const result = selectPersistableChatMessages([
      { role: "assistant", parsed: { foo: 1 }, coachText: "검증 결과", coachLoading: true },
    ]);

    expect(result).toEqual([
      {
        role: "assistant",
        parsed: { foo: 1 },
        coachText: "검증 결과",
        isLoading: false,
        coachLoading: false,
      },
    ]);
  });

  it("drops empty placeholder assistant messages that had only a loading flag", () => {
    const result = selectPersistableChatMessages([
      { role: "user", content: "PBR 1 이하 전략" },
      { role: "assistant", isLoading: true },
      { role: "assistant", coachLoading: true },
    ]);

    expect(result).toEqual([
      { role: "user", content: "PBR 1 이하 전략", isLoading: false, coachLoading: false },
    ]);
  });

  it("keeps user messages and assistant messages that carry any content", () => {
    const messages = [
      { role: "user", content: "안녕" },
      { role: "assistant", infoText: "안내" },
      { role: "assistant", error: "오류" },
      { role: "assistant", clarification: "익절 조건이 없습니다" },
    ];

    expect(selectPersistableChatMessages(messages)).toHaveLength(4);
  });
});

describe("shouldShowChatInputBox", () => {
  it("[회귀] shows the input again after the only assistant message ends in an error", () => {
    // 실사례(2026-07-05): 첫 메시지 처리 중 에러가 나면 어시스턴트 메시지가
    // { role: "assistant", error } 로만 채워져 parsed/infoText가 전부 없다.
    // 이 경우도 입력창을 다시 보여줘야 사용자가 재시도하거나 새 메시지를 보낼 수 있다.
    const messages = [
      { role: "user", content: "PBR 1 이하 전략" },
      { role: "assistant", error: "파싱 실패" },
    ];

    expect(shouldShowChatInputBox(messages, false, false)).toBe(true);
  });

  it("shows the input when idle even with no messages", () => {
    expect(shouldShowChatInputBox([], true, false)).toBe(true);
  });

  it("hides the input while the builder is awaiting a chip choice", () => {
    const messages = [
      { role: "user", content: "전략 만들래" },
      { role: "assistant", infoText: "어떤 시장을 대상으로 할까요?", infoSuggestions: ["코스피", "코스닥"] },
    ];

    expect(shouldShowChatInputBox(messages, false, false)).toBe(false);
    expect(shouldShowChatInputBox(messages, false, true)).toBe(true);
  });

  it("shows the input once a message carries parsed/infoText", () => {
    expect(
      shouldShowChatInputBox(
        [{ role: "user", content: "x" }, { role: "assistant", parsed: { foo: 1 } }],
        false,
        false
      )
    ).toBe(true);
  });

  it("hides the input while still loading (no response yet, not idle)", () => {
    const messages = [
      { role: "user", content: "PBR 1 이하 전략" },
      { role: "assistant" },
    ];

    expect(shouldShowChatInputBox(messages, false, false)).toBe(false);
  });
});
