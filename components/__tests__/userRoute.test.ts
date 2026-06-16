// @ts-nocheck
import { describe, expect, it, vi } from "vitest";

// Regression guard: /api/user must render dynamically. When it was statically
// prerendered, Next baked in {user:null} and served it from the Full Route Cache
// regardless of the request cookie, so the client AuthSessionGuard bounced
// logged-in users off every protected page back to the landing page in prod.
vi.mock("@/lib/get-user", () => ({
  getCurrentUser: () => Promise.resolve(null),
}));

const route = await import("@/app/api/user/route");

describe("/api/user route", () => {
  it("강제 동적 렌더링이어야 한다 (정적 캐시 금지 — 세션 쿠키를 매 요청마다 읽어야 함)", () => {
    expect(route.dynamic).toBe("force-dynamic");
  });
});
