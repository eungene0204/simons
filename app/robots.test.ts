import { afterEach, describe, expect, it, vi } from "vitest";
import robots from "./robots";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("robots", () => {
  it("allows the public landing and blocks private app paths under both regions", () => {
    vi.stubEnv("DOMAIN", "");
    const result = robots();
    const rule = Array.isArray(result.rules) ? result.rules[0] : result.rules;

    expect(rule.userAgent).toBe("*");
    expect(rule.allow).toBe("/");
    const disallow = Array.isArray(rule.disallow) ? rule.disallow : [rule.disallow];
    expect(disallow).toEqual(expect.arrayContaining(["/api/", "/console", "/dashboard", "/us/dashboard"]));
    expect(disallow).not.toContain("/us");
    expect(result.sitemap).toBe("https://www.nullstock.im/sitemap.xml");
  });
});
