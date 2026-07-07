// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 회귀 가드: 토큰 검증(verifySupabaseAccessToken)은 성공했는데 그 이후 DB 작업이
// 실패하면, 예전 코드는 모든 오류를 한 try/catch로 잡아 "Google 로그인 검증에
// 실패했습니다(401)"로 둔갑시켰다. 실제 사고: 프로덕션 User 테이블에 마이그레이션이
// 누락돼 findUnique가 "no such column"으로 터졌는데 토큰 문제처럼 보여 디버깅이 꼬임.
// 이제 DB 오류는 500(서버 오류)으로 드러나야 한다.

const verifySupabaseAccessToken = vi.fn();
const userFindUnique = vi.fn();
const userCreate = vi.fn();
const userUpdate = vi.fn();
const ensureUserBootstrap = vi.fn();

vi.mock("@/lib/auth", () => ({
  verifySupabaseAccessToken: (...args) => verifySupabaseAccessToken(...args),
  generateToken: () => "signed-jwt",
  hashPassword: async () => "hashed",
  verifyPassword: async () => true,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      create: (...a) => userCreate(...a),
      update: (...a) => userUpdate(...a),
    },
  },
}));

vi.mock("@/lib/get-user", () => ({
  ensureUserBootstrap: (...a) => ensureUserBootstrap(...a),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({ set: vi.fn() }),
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  POST = (await import("./route")).POST;
});

function req(body) {
  return { json: async () => body };
}

const validIdentity = {
  email: "user@example.com",
  emailVerified: true,
  name: "Tester",
  avatarUrl: null,
  uid: "uid-1",
};

describe("/api/login Google(Supabase) 경로", () => {
  it("토큰 검증 성공 후 DB 오류는 401(토큰 오인)이 아니라 500으로 드러나야 한다", async () => {
    verifySupabaseAccessToken.mockResolvedValue(validIdentity);
    // 마이그레이션 누락으로 인한 "no such column" 같은 DB 오류 시뮬레이션
    userFindUnique.mockRejectedValue(
      new Error("no such column: backtestCountThisMonth")
    );

    const res = await POST(req({ supabaseAccessToken: "valid-token" }));
    const data = await res.json();

    expect(res.status).toBe(500);
    expect(data.error).not.toBe("Google 로그인 검증에 실패했습니다.");
  });

  it("토큰 검증 자체가 실패하면 401 인증 오류를 반환한다", async () => {
    verifySupabaseAccessToken.mockRejectedValue(
      new Error("Supabase access token verification failed.")
    );

    const res = await POST(req({ supabaseAccessToken: "bad-token" }));
    const data = await res.json();

    expect(res.status).toBe(401);
    expect(data.error).toBe("Google 로그인 검증에 실패했습니다.");
    expect(userFindUnique).not.toHaveBeenCalled();
  });

  it("정상 토큰 + 기존 사용자면 200 로그인 성공", async () => {
    verifySupabaseAccessToken.mockResolvedValue(validIdentity);
    userFindUnique.mockResolvedValue({
      id: 7,
      email: "user@example.com",
      name: "Tester",
      password: "hashed",
      status: "ACTIVE",
    });
    ensureUserBootstrap.mockResolvedValue(undefined);
    userUpdate.mockResolvedValue({});

    const res = await POST(req({ supabaseAccessToken: "valid-token" }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.message).toBe("로그인 성공");
    expect(data.user.id).toBe(7);
    expect(userCreate).not.toHaveBeenCalled();
    // 로그인 성공 시 lastLoginAt을 기록한다
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: expect.objectContaining({ lastLoginAt: expect.any(Date) }),
      })
    );
  });

  it("정지(SUSPENDED) 계정은 유효한 토큰이라도 403으로 차단한다", async () => {
    verifySupabaseAccessToken.mockResolvedValue(validIdentity);
    userFindUnique.mockResolvedValue({
      id: 7,
      email: "user@example.com",
      name: "Tester",
      password: "hashed",
      status: "SUSPENDED",
    });

    const res = await POST(req({ supabaseAccessToken: "valid-token" }));

    expect(res.status).toBe(403);
    expect(ensureUserBootstrap).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });
});
