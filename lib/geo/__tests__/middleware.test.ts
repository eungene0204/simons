// 미들웨어 — `www.nullstock.im/*`는 무조건 한국 서비스다. 2026-09-15 사고: 브라우저 언어가
// 영어인 한국 방문자가 첫 방문 시 Accept-Language 폴백으로 `/`→`/us`로 튕겼다.
// 자동 지역 리다이렉트는 폐지됐고 글로벌 서비스는 `/us` 경로로만 진입한다.
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import { REGION_COOKIE, REGION_HEADER } from "@/lib/geo/region";

function request(path: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`https://www.nullstock.im${path}`, { headers });
}

describe("middleware 지역 라우팅", () => {
  it("영어 브라우저의 첫 방문도 `/`는 한국 서비스에 남긴다(리다이렉트 없음)", () => {
    const res = middleware(
      request("/", { "accept-language": "en-US,en;q=0.9", "user-agent": "Mozilla/5.0" })
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
    expect(res.headers.get("x-middleware-request-" + REGION_HEADER)).toBe("kr");
    expect(res.cookies.get(REGION_COOKIE)?.value).toBe("kr");
  });

  it("CDN 국가 헤더가 비한국이어도 `/`는 한국 서비스다", () => {
    const res = middleware(request("/", { "cf-ipcountry": "US" }));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("`/us` 경로만 글로벌 서비스로 rewrite 한다", () => {
    const res = middleware(request("/us/pricing", { "accept-language": "ko-KR" }));
    expect(res.headers.get("x-middleware-rewrite")).toBe("https://www.nullstock.im/pricing");
    expect(res.headers.get("x-middleware-request-" + REGION_HEADER)).toBe("us");
    expect(res.cookies.get(REGION_COOKIE)?.value).toBe("us");
  });
});
