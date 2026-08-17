import { afterEach, describe, expect, it } from "vitest";
import {
  __resetLanguageForTests,
  formatCompactNumberEn,
  getLanguage,
  getLocale,
  hasTranslation,
  persistLanguage,
  setLanguage,
  t,
} from "@/lib/i18n";

afterEach(() => {
  __resetLanguageForTests();
  document.cookie = "nullstock.lang=; path=/; max-age=0";
  window.localStorage.removeItem("nullstock.lang");
});

describe("t()", () => {
  it("한국어(기본)는 원문을 그대로 돌려준다", () => {
    setLanguage("ko");
    expect(t("전략연구소")).toBe("전략연구소");
    expect(t("총 {0}회 거래", 53)).toBe("총 53회 거래");
  });

  it("영어는 사전의 번역을 돌려주고 자리표시자를 치환한다", () => {
    setLanguage("en");
    expect(t("전략연구소")).toBe("Strategy Lab");
    expect(t("손절 {0}%", "-8")).toBe("Stop-loss -8%");
    expect(t("{0} ~ {1} · 최근 {2}년", "2015", "2026", 10)).toBe("2015 ~ 2026 · last 10 years");
  });

  it("사전에 없는 키는 원문으로 폴백한다(빈칸·깨진 화면 금지)", () => {
    setLanguage("en");
    expect(t("사전에 절대 없을 문장 12345")).toBe("사전에 절대 없을 문장 12345");
    expect(hasTranslation("en", "사전에 절대 없을 문장 12345")).toBe(false);
    expect(hasTranslation("ko", "무엇이든")).toBe(true);
  });

  it("칩·질문 같은 백엔드 결정론 문구도 원문 키로 번역된다", () => {
    setLanguage("en");
    expect(t("매주 리밸런싱")).toBe("Weekly rebalancing");
    expect(t("다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?")).toBe(
      "Next, shall we decide how often to rebalance the portfolio?",
    );
  });
});

describe("언어 감지·영속", () => {
  it("쿠키가 있으면 쿠키 언어로 초기화한다", () => {
    document.cookie = "nullstock.lang=en; path=/";
    expect(getLanguage()).toBe("en");
    expect(getLocale()).toBe("en-US");
  });

  it("persistLanguage는 쿠키와 localStorage에 함께 남긴다", () => {
    persistLanguage("en");
    expect(document.cookie).toContain("nullstock.lang=en");
    expect(window.localStorage.getItem("nullstock.lang")).toBe("en");
    expect(getLanguage()).toBe("en");
  });

  it("쿠키·저장소가 없으면 한국어가 기본이다", () => {
    expect(getLanguage()).toBe("ko");
    expect(getLocale()).toBe("ko-KR");
  });
});

describe("formatCompactNumberEn", () => {
  it("한국어에서는 null(호출자의 억/만 표기 사용)", () => {
    setLanguage("ko");
    expect(formatCompactNumberEn(150_000_000)).toBeNull();
  });

  it("영어에서는 compact 표기", () => {
    setLanguage("en");
    expect(formatCompactNumberEn(150_000_000)).toBe("150M");
    expect(formatCompactNumberEn(2_500_000_000, { withCurrency: true })).toBe("₩2.5B");
  });
});
