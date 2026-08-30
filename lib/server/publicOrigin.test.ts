import { describe, expect, it } from "vitest";
import { publicOriginFrom } from "./publicOrigin";

function req(headers: Record<string, string>) {
  return { headers: new Headers(headers) } as Request;
}

describe("publicOriginFrom", () => {
  // 회귀(2026-08-31): request.url이 컨테이너 내부 주소라 PayPal 복귀가 localhost로 떨어졌다
  it("프록시 뒤에서는 방문자의 Host 헤더로 origin을 만든다", () => {
    expect(
      publicOriginFrom(req({ host: "www.nullstock.im", "x-forwarded-proto": "https" }))
    ).toBe("https://www.nullstock.im");
  });

  it("x-forwarded-host가 있으면 그것을 우선한다(콤마 목록은 첫 값)", () => {
    expect(
      publicOriginFrom(
        req({ host: "web:3000", "x-forwarded-host": "www.nullstock.im, caddy", "x-forwarded-proto": "https" })
      )
    ).toBe("https://www.nullstock.im");
  });

  it("로컬 개발(localhost)은 http로 만든다", () => {
    expect(publicOriginFrom(req({ host: "localhost:3000" }))).toBe("http://localhost:3000");
  });

  it("프록시 헤더 없는 외부 호스트는 https로 본다", () => {
    expect(publicOriginFrom(req({ host: "www.nullstock.im" }))).toBe("https://www.nullstock.im");
  });
});
