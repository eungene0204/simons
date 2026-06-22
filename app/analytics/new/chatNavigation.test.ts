import { afterEach, describe, expect, it, vi } from "vitest";

import {
  beginStrategyChatNavigation,
  selectPersistableChatMessages,
  shouldBeginStrategyChatNavigation,
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
    expect(navigate).toHaveBeenCalledWith("/analytics/chat");
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
        stockLoading: false,
        coachLoading: false,
      },
    ]);
  });

  it("drops empty placeholder assistant messages that had only a loading flag", () => {
    const result = selectPersistableChatMessages([
      { role: "user", content: "PBR 1 이하 전략" },
      { role: "assistant", isLoading: true },
      { role: "assistant", coachLoading: true },
      { role: "assistant", stockLoading: true },
    ]);

    expect(result).toEqual([
      { role: "user", content: "PBR 1 이하 전략", isLoading: false, stockLoading: false, coachLoading: false },
    ]);
  });

  it("keeps user messages and assistant messages that carry any content", () => {
    const messages = [
      { role: "user", content: "안녕" },
      { role: "assistant", infoText: "안내" },
      { role: "assistant", error: "오류" },
      { role: "assistant", stockAnalysis: { symbol: "005930" } },
      { role: "assistant", clarification: "익절 조건이 없습니다" },
    ];

    expect(selectPersistableChatMessages(messages)).toHaveLength(5);
  });
});
