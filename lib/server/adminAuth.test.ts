// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 보안 핵심: requireAdmin은 로그인 + ADMIN 역할 + ACTIVE 상태를 모두 서버에서 검증한다.
// 하나라도 실패하면 null → 호출측은 404로 응답해 콘솔 존재를 숨긴다.

const getCookie = vi.fn();
const verifyToken = vi.fn();
const userFindUnique = vi.fn();
const auditCreate = vi.fn();

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (...a) => getCookie(...a) }),
  headers: async () => ({
    get: (name) => (name === "x-forwarded-for" ? "10.0.0.1, 172.16.0.1" : null),
  }),
}));

vi.mock("@/lib/auth", () => ({
  verifyToken: (...a) => verifyToken(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { findUnique: (...a) => userFindUnique(...a) },
    adminAuditLog: { create: (...a) => auditCreate(...a) },
  },
}));

let requireAdmin;
let writeAuditLog;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ requireAdmin, writeAuditLog } = await import("@/lib/server/adminAuth"));
});

const adminRecord = {
  id: 1,
  email: "admin@example.com",
  name: "Admin",
  role: "ADMIN",
  status: "ACTIVE",
};

describe("requireAdmin", () => {
  it("토큰이 없으면 null", async () => {
    getCookie.mockReturnValue(undefined);
    expect(await requireAdmin()).toBeNull();
    expect(userFindUnique).not.toHaveBeenCalled();
  });

  it("토큰 검증 실패면 null", async () => {
    getCookie.mockReturnValue({ value: "bad" });
    verifyToken.mockReturnValue(null);
    expect(await requireAdmin()).toBeNull();
  });

  it("일반 사용자(role=USER)면 null", async () => {
    getCookie.mockReturnValue({ value: "jwt" });
    verifyToken.mockReturnValue({ userId: 2 });
    userFindUnique.mockResolvedValue({ ...adminRecord, id: 2, role: "USER" });
    expect(await requireAdmin()).toBeNull();
  });

  it("정지된 관리자(status=SUSPENDED)면 null", async () => {
    getCookie.mockReturnValue({ value: "jwt" });
    verifyToken.mockReturnValue({ userId: 1 });
    userFindUnique.mockResolvedValue({ ...adminRecord, status: "SUSPENDED" });
    expect(await requireAdmin()).toBeNull();
  });

  it("활성 ADMIN이면 사용자 정보를 반환한다", async () => {
    getCookie.mockReturnValue({ value: "jwt" });
    verifyToken.mockReturnValue({ userId: 1 });
    userFindUnique.mockResolvedValue(adminRecord);

    expect(await requireAdmin()).toEqual({
      id: 1,
      email: "admin@example.com",
      name: "Admin",
    });
  });

  it("DB 오류 시에도 throw하지 않고 null(접근 거부)", async () => {
    getCookie.mockReturnValue({ value: "jwt" });
    verifyToken.mockReturnValue({ userId: 1 });
    userFindUnique.mockRejectedValue(new Error("db down"));
    expect(await requireAdmin()).toBeNull();
  });
});

describe("writeAuditLog", () => {
  it("작업 내용을 before/after JSON과 IP(x-forwarded-for 첫 항목)로 기록한다", async () => {
    auditCreate.mockResolvedValue({});

    await writeAuditLog(
      { id: 1, email: "admin@example.com", name: "Admin" },
      {
        action: "USER_SUSPEND",
        targetType: "USER",
        targetId: "7",
        targetUserId: 7,
        before: { status: "ACTIVE" },
        after: { status: "SUSPENDED" },
      }
    );

    expect(auditCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        adminId: 1,
        adminEmail: "admin@example.com",
        action: "USER_SUSPEND",
        targetUserId: 7,
        beforeJson: JSON.stringify({ status: "ACTIVE" }),
        afterJson: JSON.stringify({ status: "SUSPENDED" }),
        ip: "10.0.0.1",
      }),
    });
  });
});
