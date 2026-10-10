import { describe, expect, it } from "vitest";
import {
  MAX_STRATEGY_PROMPT_LENGTH,
  readStrategyPromptParam,
  withoutStrategyPromptParam,
} from "./strategyOpenLink";

describe("readStrategyPromptParam", () => {
  it("인코딩된 한국어 문장을 그대로 돌려준다", () => {
    const prompt = "KOSPI 종목 중 RSI가 30 아래로 내려가면 매수하고, 손절은 -8%로 해 주세요.";
    const params = new URLSearchParams(`prompt=${encodeURIComponent(prompt)}&utm_source=x`);
    expect(readStrategyPromptParam(params)).toBe(prompt);
  });

  it("없거나 공백뿐이면 null", () => {
    expect(readStrategyPromptParam(new URLSearchParams(""))).toBeNull();
    expect(readStrategyPromptParam(new URLSearchParams("prompt=%20%20"))).toBeNull();
  });

  it("한도를 넘는 긴 값은 채우지 않는다", () => {
    const long = "가".repeat(MAX_STRATEGY_PROMPT_LENGTH + 1);
    expect(readStrategyPromptParam(new URLSearchParams({ prompt: long }))).toBeNull();
  });
});

describe("withoutStrategyPromptParam", () => {
  it("prompt만 걷어내고 utm은 남긴다", () => {
    expect(withoutStrategyPromptParam("/analytics/new", "?prompt=abc&utm_source=x&utm_campaign=myth")).toBe(
      "/analytics/new?utm_source=x&utm_campaign=myth",
    );
  });

  it("남는 파라미터가 없으면 경로만", () => {
    expect(withoutStrategyPromptParam("/analytics/new", "?prompt=abc")).toBe("/analytics/new");
  });
});
