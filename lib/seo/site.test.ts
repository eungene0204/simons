import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildHomeJsonLd,
  buildOpenGraph,
  robotsDisallowPaths,
  serializeJsonLd,
  SITE_DESCRIPTION,
  SITE_TITLE,
  siteUrl,
  siteVerification,
} from "./site";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("siteUrl", () => {
  it("uses the DOMAIN env when set and the canonical www host otherwise", () => {
    vi.stubEnv("DOMAIN", "staging.nullstock.im");
    expect(siteUrl()).toBe("https://staging.nullstock.im");
    vi.stubEnv("DOMAIN", "");
    expect(siteUrl()).toBe("https://www.nullstock.im");
  });
});

describe("site copy", () => {
  it("leads the Korean title and description with the target search terms", () => {
    expect(SITE_TITLE.ko).toMatch(/퀀트/);
    expect(SITE_TITLE.ko).toMatch(/백테스트/);
    expect(SITE_DESCRIPTION.ko).toMatch(/퀀트/);
    expect(SITE_DESCRIPTION.ko).toMatch(/백테스트/);
  });

  it("never uses recommendation or forecast wording (regulatory guard)", () => {
    const copy = [SITE_TITLE.ko, SITE_DESCRIPTION.ko, ...Object.values(buildHomeJsonLd("ko")).map(String)].join(" ");
    expect(copy).not.toMatch(/추천|유망|보장|전망/);
  });
});

describe("buildOpenGraph", () => {
  it("fills siteName and locale per language so page-level overrides keep them", () => {
    expect(buildOpenGraph("ko", { title: "T", description: "D", url: "/" })).toMatchObject({
      type: "website",
      siteName: "널스탁",
      locale: "ko_KR",
      title: "T",
      description: "D",
      url: "/",
    });
    expect(buildOpenGraph("en", { title: "T", description: "D", url: "/us" })).toMatchObject({
      siteName: "NullStock",
      locale: "en_US",
      url: "/us",
    });
  });
});

describe("siteVerification", () => {
  it("returns undefined when neither token is configured", () => {
    expect(siteVerification({})).toBeUndefined();
    expect(siteVerification({ GOOGLE_SITE_VERIFICATION: "  ", NAVER_SITE_VERIFICATION: "" })).toBeUndefined();
  });

  it("maps Google and Naver tokens to their meta names", () => {
    expect(siteVerification({ GOOGLE_SITE_VERIFICATION: "g-1", NAVER_SITE_VERIFICATION: "n-1" })).toEqual({
      google: "g-1",
      other: { "naver-site-verification": "n-1" },
    });
    expect(siteVerification({ NAVER_SITE_VERIFICATION: "n-1" })).toEqual({
      other: { "naver-site-verification": "n-1" },
    });
  });
});

describe("buildHomeJsonLd", () => {
  it("links Organization, WebSite and WebApplication on the regional home URL", () => {
    const ko = buildHomeJsonLd("ko", "https://www.nullstock.im");
    const graph = ko["@graph"] as Array<Record<string, unknown>>;
    expect(graph.map((node) => node["@type"])).toEqual(["Organization", "WebSite", "WebApplication"]);
    expect(graph[0]).toMatchObject({
      "@id": "https://www.nullstock.im/#organization",
      name: "널스탁",
      logo: "https://www.nullstock.im/nullStock.png",
    });
    expect(graph[1]).toMatchObject({ url: "https://www.nullstock.im", inLanguage: "ko-KR" });
    expect(graph[2]).toMatchObject({
      applicationCategory: "FinanceApplication",
      offers: { price: "0", priceCurrency: "KRW" },
      publisher: { "@id": "https://www.nullstock.im/#organization" },
    });

    const en = buildHomeJsonLd("en", "https://www.nullstock.im");
    const enGraph = en["@graph"] as Array<Record<string, unknown>>;
    expect(enGraph[1]).toMatchObject({ url: "https://www.nullstock.im/us", inLanguage: "en-US" });
    expect(enGraph[2]).toMatchObject({ offers: { priceCurrency: "USD" } });
  });

  it("escapes < so the JSON cannot close the script tag early", () => {
    expect(serializeJsonLd({ a: "</script>" })).toBe('{"a":"\\u003c/script>"}');
  });
});

describe("robotsDisallowPaths", () => {
  it("blocks every private app path under both region prefixes", () => {
    const paths = robotsDisallowPaths();
    for (const path of ["/api/", "/console", "/dashboard", "/backtest", "/virtual-account", "/login"]) {
      expect(paths).toContain(path);
      expect(paths).toContain(`/us${path}`);
    }
    expect(paths).not.toContain("/");
    expect(paths).not.toContain("/pricing");
  });
});
