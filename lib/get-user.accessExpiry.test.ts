// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 이용 기한이 지난 계정은 유효한 토큰이 남아 있어도 세션을 인정하지 않는다(2026-09-17 게스트 입장 링크 기한).
const { userFindUnique } = vi.hoisted(() => ({ userFindUnique: vi.fn() }));

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "tok" }) }) }));
vi.mock("./auth", () => ({ verifyToken: () => ({ userId: 42 }) }));
vi.mock("./prisma", () => ({ prisma: { user: { findUnique: userFindUnique } } }));

const { getCurrentUser, assertActiveUser, UnauthorizedAccessError } = await import("./get-user");

const guest = { id: 42, email: "guest_1234@guest.nullstock.im", name: "guest_1234", status: "ACTIVE" };

describe("세션 인정 — 이용 기한", () => {
  beforeEach(() => userFindUnique.mockReset());

  it("기한 안이면 getCurrentUser·assertActiveUser 모두 통과", async () => {
    userFindUnique.mockResolvedValue({ ...guest, accessExpiresAt: new Date(Date.now() + 60_000) });
    expect((await getCurrentUser())?.id).toBe(42);
    await expect(assertActiveUser(42)).resolves.toBeUndefined();
  });

  it("기한이 지나면 getCurrentUser는 null, assertActiveUser는 거부", async () => {
    userFindUnique.mockResolvedValue({ ...guest, accessExpiresAt: new Date(Date.now() - 1) });
    expect(await getCurrentUser()).toBeNull();
    await expect(assertActiveUser(42)).rejects.toBeInstanceOf(UnauthorizedAccessError);
  });
});
