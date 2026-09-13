import { afterEach, describe, expect, it, vi } from "vitest";

// generateMetadata만 검증한다 — 레이아웃이 끌어오는 클라이언트 컴포넌트는 비운다.
vi.mock("./globals.css", () => ({}));
vi.mock("@/components/layout/TopMenuBar", () => ({ default: () => null }));
vi.mock("@/components/layout/ScrollToTop", () => ({ default: () => null }));
vi.mock("@/components/layout/VisualViewportInset", () => ({ default: () => null }));
vi.mock("@/components/providers/QueryProvider", () => ({ default: () => null }));
vi.mock("@/contexts/OrderAccountContext", () => ({ OrderAccountProvider: () => null }));
vi.mock("@/components/ChunkErrorRecovery", () => ({ default: () => null }));
vi.mock("@/lib/i18n/LanguageProvider", () => ({ LanguageProvider: () => null }));
vi.mock("@next/third-parties/google", () => ({ GoogleAnalytics: () => null }));
// next/font는 빌드 시 폰트를 내려받는 컴파일러 훅이라 vitest에서는 함수가 아니다 — 변수명만 돌려준다.
vi.mock("next/font/google", () => ({
  Noto_Serif_KR: () => ({ variable: "--font-serif-mock", className: "" }),
}));

const languageMock = vi.hoisted(() => ({ value: "ko" as "ko" | "en" }));
vi.mock("@/lib/i18n/server", () => ({
  getRequestLanguage: () => languageMock.value,
}));

import { generateMetadata } from "./layout";

afterEach(() => {
  vi.unstubAllEnvs();
  languageMock.value = "ko";
});

describe("root layout metadata", () => {
  it("publishes keyword-led Korean title, template, Open Graph and Twitter card", () => {
    vi.stubEnv("DOMAIN", "");
    const metadata = generateMetadata();

    expect(metadata.metadataBase?.toString()).toBe("https://www.nullstock.im/");
    expect(metadata.title).toEqual({
      default: "널스탁 | 퀀트 전략 백테스트·시뮬레이션 플랫폼",
      template: "%s | 널스탁",
    });
    expect(metadata.description).toMatch(/퀀트.*백테스트/);
    expect(metadata.keywords).toEqual(expect.arrayContaining(["퀀트", "백테스트"]));
    expect(metadata.robots).toEqual({ index: true, follow: true });
    expect(metadata.openGraph).toMatchObject({ siteName: "널스탁", locale: "ko_KR", url: "/" });
    expect(metadata.twitter).toMatchObject({ card: "summary_large_image" });
    expect(metadata.verification).toBeUndefined();
  });

  it("switches to English copy and the /us home for the global service", () => {
    languageMock.value = "en";
    const metadata = generateMetadata();

    expect(metadata.title).toEqual({
      default: "NullStock | Quant Strategy Backtesting Platform for U.S. Stocks",
      template: "%s | NullStock",
    });
    expect(metadata.openGraph).toMatchObject({ siteName: "NullStock", locale: "en_US", url: "/us" });
  });

  it("emits Google and Naver site-verification tokens from the environment", () => {
    vi.stubEnv("GOOGLE_SITE_VERIFICATION", "google-token");
    vi.stubEnv("NAVER_SITE_VERIFICATION", "naver-token");

    expect(generateMetadata().verification).toEqual({
      google: "google-token",
      other: { "naver-site-verification": "naver-token" },
    });
  });
});
