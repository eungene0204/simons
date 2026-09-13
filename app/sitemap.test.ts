import { afterEach, describe, expect, it, vi } from "vitest";
import sitemap from "./sitemap";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("sitemap", () => {
  it("lists only public entry points and pairs the two regional homes with hreflang", () => {
    vi.stubEnv("DOMAIN", "");
    const entries = sitemap();
    const urls = entries.map((entry) => entry.url);

    expect(urls).toEqual([
      "https://www.nullstock.im",
      "https://www.nullstock.im/us",
      "https://www.nullstock.im/us/pricing",
    ]);
    // 한국 요금제는 비로그인 요청을 `/`로 리다이렉트한다 — 리다이렉트 URL은 사이트맵에 넣지 않는다.
    expect(urls).not.toContain("https://www.nullstock.im/pricing");

    const home = entries[0];
    expect(home.priority).toBe(1);
    expect(home.alternates?.languages).toEqual({
      "ko-KR": "https://www.nullstock.im",
      "en-US": "https://www.nullstock.im/us",
      "x-default": "https://www.nullstock.im",
    });
    expect(entries[1].alternates?.languages).toEqual(home.alternates?.languages);
  });

  it("follows the DOMAIN env for absolute URLs", () => {
    vi.stubEnv("DOMAIN", "staging.nullstock.im");
    expect(sitemap()[0].url).toBe("https://staging.nullstock.im");
  });
});
