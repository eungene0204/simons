// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 배치 실행 라우트는 내부 도구 — 관리자 외에는 403(2026-09-03 감사: 무인증으로 열려 있었다).
const { requireAdmin } = vi.hoisted(() => ({ requireAdmin: vi.fn() }));
vi.mock("@/lib/server/adminAuth", () => ({ requireAdmin }));
vi.mock("@/lib/prisma", () => ({ prisma: { batchRun: { findMany: vi.fn(async () => []), findUnique: vi.fn() } } }));

const { GET, POST } = await import("./route");

describe("/api/strategy/batch-runs 관리자 게이트", () => {
  beforeEach(() => vi.clearAllMocks());

  it("비관리자·비로그인은 403", async () => {
    requireAdmin.mockResolvedValue(null);
    const req = { nextUrl: new URL("http://localhost/api/strategy/batch-runs"), json: async () => ({}) } as any;
    expect((await GET(req)).status).toBe(403);
    expect((await POST(req)).status).toBe(403);
  });
});
