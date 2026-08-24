import { describe, expect, it } from "vitest";
import {
  regionFromPathname,
  stripRegionPrefix,
  withRegionPath,
} from "@/lib/geo/region";
import {
  countryFromHeaders,
  isKnownBot,
  prefersKorean,
  resolvePreferredRegion,
} from "@/lib/geo/country";

describe("regionFromPathname", () => {
  it("/us 트리만 us다", () => {
    expect(regionFromPathname("/us")).toBe("us");
    expect(regionFromPathname("/us/backtest")).toBe("us");
    expect(regionFromPathname("/")).toBe("kr");
    expect(regionFromPathname("/backtest")).toBe("kr");
    // 프리픽스가 낱말 경계로 끝나야 한다 — /user는 한국 트리
    expect(regionFromPathname("/user")).toBe("kr");
    expect(regionFromPathname(null)).toBe("kr");
  });
});

describe("stripRegionPrefix", () => {
  it("us 프리픽스를 벗긴다", () => {
    expect(stripRegionPrefix("/us")).toBe("/");
    expect(stripRegionPrefix("/us/pricing")).toBe("/pricing");
    expect(stripRegionPrefix("/pricing")).toBe("/pricing");
    expect(stripRegionPrefix("/user")).toBe("/user");
  });
});

describe("withRegionPath", () => {
  it("kr은 경로를 그대로 둔다", () => {
    expect(withRegionPath("kr", "/pricing")).toBe("/pricing");
  });

  it("us는 /us 프리픽스를 붙인다", () => {
    expect(withRegionPath("us", "/pricing")).toBe("/us/pricing");
    expect(withRegionPath("us", "/")).toBe("/us");
  });

  it("쿼리·해시를 보존한다", () => {
    expect(withRegionPath("us", "/?legal=terms")).toBe("/us?legal=terms");
    expect(withRegionPath("us", "/stock-order?symbol=AAPL")).toBe(
      "/us/stock-order?symbol=AAPL"
    );
    expect(withRegionPath("us", "/pricing#plans")).toBe("/us/pricing#plans");
  });

  it("이미 프리픽스된 경로·외부 URL은 그대로 둔다(이중 프리픽스 금지)", () => {
    expect(withRegionPath("us", "/us/pricing")).toBe("/us/pricing");
    expect(withRegionPath("us", "https://example.com/a")).toBe("https://example.com/a");
    expect(withRegionPath("us", "#section")).toBe("#section");
  });
});

describe("countryFromHeaders", () => {
  it("지오 헤더를 우선순위대로 읽는다", () => {
    expect(countryFromHeaders((n) => (n === "cf-ipcountry" ? "US" : null))).toBe("US");
    expect(countryFromHeaders((n) => (n === "x-geo-country" ? "kr" : null))).toBe("KR");
    expect(countryFromHeaders(() => null)).toBeNull();
    // Cloudflare의 미상 국가(XX)는 신호 없음으로 취급
    expect(countryFromHeaders((n) => (n === "cf-ipcountry" ? "XX" : null))).toBeNull();
  });
});

describe("prefersKorean", () => {
  it("Accept-Language의 한국어 포함 여부", () => {
    expect(prefersKorean("ko-KR,ko;q=0.9,en-US;q=0.8")).toBe(true);
    expect(prefersKorean("en-US,en;q=0.9")).toBe(false);
    expect(prefersKorean(null)).toBeNull();
    expect(prefersKorean("")).toBeNull();
  });
});

describe("resolvePreferredRegion", () => {
  const headers = (map: Record<string, string>) => (name: string) => map[name] ?? null;

  it("국가 헤더가 최우선이다", () => {
    expect(
      resolvePreferredRegion(headers({ "cf-ipcountry": "KR", "accept-language": "en-US" }))
    ).toBe("kr");
    expect(
      resolvePreferredRegion(headers({ "cf-ipcountry": "US", "accept-language": "ko-KR" }))
    ).toBe("us");
  });

  it("국가 헤더가 없으면 Accept-Language로 폴백한다", () => {
    expect(resolvePreferredRegion(headers({ "accept-language": "en-US,en;q=0.9" }))).toBe("us");
    expect(resolvePreferredRegion(headers({ "accept-language": "ko-KR,ko;q=0.9" }))).toBe("kr");
  });

  it("신호가 전혀 없으면 한국(기본)이다", () => {
    expect(resolvePreferredRegion(() => null)).toBe("kr");
  });
});

describe("isKnownBot", () => {
  it("크롤러 UA를 식별한다", () => {
    expect(isKnownBot("Mozilla/5.0 (compatible; Googlebot/2.1)")).toBe(true);
    expect(isKnownBot("Yeti/1.1 (Naver Corp.)")).toBe(true);
    expect(isKnownBot("Mozilla/5.0 (Macintosh) Safari/605.1")).toBe(false);
    expect(isKnownBot(null)).toBe(false);
  });
});
