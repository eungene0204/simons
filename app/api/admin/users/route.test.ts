// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 보안 회귀 가드: 모든 /api/admin/* 는 requireAdmin 실패 시 404를 반환해
// 관리자 API의 존재 자체를 숨긴다. 관리자 작업은 반드시 감사 로그를 남긴다.

const requireAdmin = vi.fn();
const writeAuditLog = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const userFindMany = vi.fn();
const userCount = vi.fn();

vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: (...a) => requireAdmin(...a),
  writeAuditLog: (...a) => writeAuditLog(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
      findMany: (...a) => userFindMany(...a),
      count: (...a) => userCount(...a),
    },
    planConfig: { findUnique: vi.fn().mockResolvedValue(null) },
  },
}));

let GET;
let PATCH;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ GET, PATCH } = await import("./route"));
});

const admin = { id: 1, email: "admin@example.com", name: "Admin" };

function getReq(query = "") {
  return { nextUrl: new URL(`http://localhost/api/admin/users${query}`) };
}

function patchReq(body) {
  return { json: async () => body };
}

describe("/api/admin/users 권한 게이트", () => {
  it("비관리자는 GET에서 404 (존재 자체를 숨김)", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await GET(getReq());
    expect(res.status).toBe(404);
    expect(userFindMany).not.toHaveBeenCalled();
  });

  it("비관리자는 PATCH에서 404, 어떤 작업도 수행하지 않는다", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await PATCH(patchReq({ userId: 7, action: "suspend" }));
    expect(res.status).toBe(404);
    expect(userUpdate).not.toHaveBeenCalled();
    expect(writeAuditLog).not.toHaveBeenCalled();
  });
});

describe("/api/admin/users PATCH 작업", () => {
  beforeEach(() => {
    requireAdmin.mockResolvedValue(admin);
    writeAuditLog.mockResolvedValue(undefined);
    userUpdate.mockResolvedValue({});
  });

  it("suspend: 상태를 SUSPENDED로 바꾸고 감사 로그를 남긴다", async () => {
    userFindUnique.mockResolvedValue({
      id: 7,
      email: "u@example.com",
      planTier: "FREE",
      status: "ACTIVE",
      role: "USER",
    });

    const res = await PATCH(patchReq({ userId: 7, action: "suspend" }));

    expect(res.status).toBe(200);
    expect(userUpdate).toHaveBeenCalledWith({
      where: { id: 7 },
      data: { status: "SUSPENDED" },
    });
    expect(writeAuditLog).toHaveBeenCalledWith(
      admin,
      expect.objectContaining({
        action: "USER_SUSPEND",
        targetUserId: 7,
        before: { status: "ACTIVE" },
        after: { status: "SUSPENDED" },
      })
    );
  });

  it("changePlan: 잘못된 planTier는 400", async () => {
    userFindUnique.mockResolvedValue({
      id: 7,
      email: "u@example.com",
      planTier: "FREE",
      status: "ACTIVE",
      role: "USER",
    });

    const res = await PATCH(
      patchReq({ userId: 7, action: "changePlan", planTier: "ULTRA" })
    );

    expect(res.status).toBe(400);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("자기 자신 정지/삭제는 차단한다 (콘솔 잠금 사고 방지)", async () => {
    userFindUnique.mockResolvedValue({
      id: 1,
      email: "admin@example.com",
      planTier: "FREE",
      status: "ACTIVE",
      role: "ADMIN",
    });

    const res = await PATCH(patchReq({ userId: 1, action: "suspend" }));

    expect(res.status).toBe(400);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("존재하지 않는 사용자는 404", async () => {
    userFindUnique.mockResolvedValue(null);
    const res = await PATCH(patchReq({ userId: 999, action: "suspend" }));
    expect(res.status).toBe(404);
  });
});
