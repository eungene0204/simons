import { describe, expect, it } from "vitest";
import {
  compactSearchText,
  getInitialConsonants,
  scoreSmartMatch,
} from "@/lib/smart-search";

describe("smart search matching", () => {
  it("공백을 제거한 비교가 가능하다", () => {
    expect(compactSearchText("  삼 성 전 자  ")).toBe("삼성전자");
  });

  it("한글 초성을 추출한다", () => {
    expect(getInitialConsonants("삼성전자")).toBe("ㅅㅅㅈㅈ");
  });

  it("부분 문자열 입력도 높은 점수로 매칭된다", () => {
    expect(scoreSmartMatch("삼성", ["삼성전자"])).toBeGreaterThan(500);
  });

  it("초성 입력도 매칭된다", () => {
    expect(scoreSmartMatch("ㅅㅅ", ["삼성전자"])).toBeGreaterThan(300);
  });

  it("연속되지 않은 축약 입력도 순서 기반으로 매칭된다", () => {
    expect(scoreSmartMatch("삼전", ["삼성전자"])).toBeGreaterThan(300);
  });

  it("전혀 다른 단어는 0점이다", () => {
    expect(scoreSmartMatch("네이버", ["삼성전자"])).toBe(0);
  });
});
