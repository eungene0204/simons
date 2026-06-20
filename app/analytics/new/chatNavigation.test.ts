import { afterEach, describe, expect, it, vi } from "vitest";

import {
  beginStrategyChatNavigation,
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
