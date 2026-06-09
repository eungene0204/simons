import { describe, it, expect } from "vitest";
import { parseCoachSegments } from "./coachText";

describe("parseCoachSegments", () => {
  it("splits a markdown link token into a link segment", () => {
    const segments = parseCoachSegments(
      "[뉴스](https://news.example.com/a1) 분석 결과 익절 비율을 고려하세요."
    );
    expect(segments[0]).toEqual({
      type: "link",
      value: "뉴스",
      href: "https://news.example.com/a1",
    });
    expect(segments[1]).toEqual({
      type: "text",
      value: " 분석 결과 익절 비율을 고려하세요.",
    });
  });

  it("strips bold markers from plain text", () => {
    const segments = parseCoachSegments("**손절** 기준을 추가하세요.");
    expect(segments).toEqual([
      { type: "text", value: "손절 기준을 추가하세요." },
    ]);
  });

  it("returns a single text segment when there is no link", () => {
    const segments = parseCoachSegments("뉴스 분석 결과를 참고하세요.");
    expect(segments).toEqual([
      { type: "text", value: "뉴스 분석 결과를 참고하세요." },
    ]);
  });

  it("keeps text before and after a link", () => {
    const segments = parseCoachSegments(
      "최근 [뉴스](https://e.com/x)를 보면 변동성이 큽니다."
    );
    expect(segments.map((s) => s.type)).toEqual(["text", "link", "text"]);
    expect(segments[0]).toEqual({ type: "text", value: "최근 " });
    expect(segments[2]).toEqual({ type: "text", value: "를 보면 변동성이 큽니다." });
  });
});
