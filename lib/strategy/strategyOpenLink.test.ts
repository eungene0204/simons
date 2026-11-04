import { describe, expect, it } from "vitest";
import {
  MAX_STRATEGY_PROMPT_LENGTH,
  readStrategyPromptParam,
  strategyOpenHref,
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

describe("strategyOpenHref", () => {
  it("홈 주소에 문장과 유입 구분값을 싣고, 앱이 같은 문장으로 읽는다", () => {
    const prompt = "KOSPI에서 5일 이동평균선이 20일 이동평균선을 위로 뚫으면 매수해 주세요.";
    const href = strategyOpenHref(prompt, "notes", "myth-09-ma-5-20-cross")!;
    expect(href.startsWith("/?")).toBe(true);
    const params = new URLSearchParams(href.slice(2));
    expect(readStrategyPromptParam(params)).toBe(prompt);
    expect(params.get("utm_source")).toBe("notes");
    expect(params.get("utm_campaign")).toBe("myth-09-ma-5-20-cross");
  });

  it("앱이 채우지 않을 문장(빈 값·한도 초과)이면 링크를 만들지 않는다", () => {
    expect(strategyOpenHref("  ", "notes", "c")).toBeUndefined();
    expect(strategyOpenHref("가".repeat(MAX_STRATEGY_PROMPT_LENGTH + 1), "notes", "c")).toBeUndefined();
  });
});
