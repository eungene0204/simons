// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 게스트(테스터) 입장 API 회귀 가드 — 아이디는 합성 이메일로만 조회되고, 짧은 비밀번호는
// 레이트리밋이 보호하며, 성공 시 /api/login과 같은 쿠키 계약을 따른다.

const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const ensureUserBootstrap = vi.fn();
const verifyPassword = vi.fn();
const cookieSet = vi.fn();

vi.mock("@/lib/auth", () => ({
  generateToken: () => "signed-jwt",
  verifyPassword: (...a) => verifyPassword(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
  },
}));

vi.mock("@/lib/get-user", () => ({
  ensureUserBootstrap: (...a) => ensureUserBootstrap(...a),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({ set: (...a) => cookieSet(...a) }),
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  const { __resetRateLimitForTests } = await import("@/lib/server/rate-limit");
  __resetRateLimitForTests();
  POST = (await import("./route")).POST;
});

function req(body, ip = "10.0.0.1") {
  return {
    json: async () => body,
    headers: new Headers({ "x-forwarded-for": ip }),
  };
}

const activeGuest = {
  id: 42,
  email: "guest_1234@guest.nullstock.im",
  name: "guest_1234",
  password: "hashed",
  status: "ACTIVE",
};

describe("/api/guest/login", () => {
  it("아이디·비밀번호가 비면 400", async () => {
    const res = await POST(req({ guestId: "", password: "" }));
    expect(res.status).toBe(400);
    expect(userFindUnique).not.toHaveBeenCalled();
  });

  it("guest_ 형식이 아닌 아이디는 DB를 보지 않고 401", async () => {
    const res = await POST(req({ guestId: "admin@nullstock.im", password: "abcde" }));
    expect(res.status).toBe(401);
    expect(userFindUnique).not.toHaveBeenCalled();
  });

  it("아이디를 합성 이메일로 바꿔 조회한다(공백·대문자 정규화)", async () => {
    userFindUnique.mockResolvedValue(null);
    const res = await POST(req({ guestId: " Guest_1234 ", password: "abcde" }));
    expect(res.status).toBe(401);
    expect(userFindUnique).toHaveBeenCalledWith({
      where: { email: "guest_1234@guest.nullstock.im" },
    });
  });

  it("비밀번호 불일치는 401", async () => {
    userFindUnique.mockResolvedValue(activeGuest);
    verifyPassword.mockResolvedValue(false);
    const res = await POST(req({ guestId: "guest_1234", password: "wrong" }));
    expect(res.status).toBe(401);
    expect(cookieSet).not.toHaveBeenCalled();
  });

  it("정지된 계정은 403", async () => {
    userFindUnique.mockResolvedValue({ ...activeGuest, status: "SUSPENDED" });
    verifyPassword.mockResolvedValue(true);
    const res = await POST(req({ guestId: "guest_1234", password: "abcde" }));
    expect(res.status).toBe(403);
    expect(cookieSet).not.toHaveBeenCalled();
  });

  it("이용 기한이 지난 계정은 403(이용 기간 종료 안내), 쿠키 없음", async () => {
    userFindUnique.mockResolvedValue({ ...activeGuest, accessExpiresAt: new Date(Date.now() - 1000) });
    verifyPassword.mockResolvedValue(true);
    const res = await POST(req({ guestId: "guest_1234", password: "abcde" }));
    expect(res.status).toBe(403);
    expect((await res.json()).error).toBe("이용 기간이 끝난 계정입니다.");
    expect(cookieSet).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("성공 시 부트스트랩·최근 로그인 갱신·httpOnly 쿠키 발급", async () => {
    userFindUnique.mockResolvedValue(activeGuest);
    verifyPassword.mockResolvedValue(true);
    userUpdate.mockResolvedValue({});
    const res = await POST(req({ guestId: "guest_1234", password: "abcde" }));
    const data = await res.json();
    expect(res.status).toBe(200);
    expect(data.user).toEqual({
      id: 42,
      email: "guest_1234@guest.nullstock.im",
      name: "guest_1234",
      avatarUrl: null,
    });
    expect(ensureUserBootstrap).toHaveBeenCalledWith(42);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ where: { id: 42 } })
    );
    expect(cookieSet).toHaveBeenCalledWith(
      "token",
      "signed-jwt",
      expect.objectContaining({ httpOnly: true, sameSite: "lax" })
    );
  });

  it("같은 아이디로 10회를 넘기면 429 — 짧은 비밀번호 무차별 대입 차단", async () => {
    userFindUnique.mockResolvedValue(activeGuest);
    verifyPassword.mockResolvedValue(false);
    for (let i = 0; i < 10; i++) {
      const res = await POST(req({ guestId: "guest_1234", password: "wrong" }, `10.0.0.${i}`));
      expect(res.status).toBe(401);
    }
    const blocked = await POST(req({ guestId: "guest_1234", password: "abcde" }, "10.0.0.99"));
    expect(blocked.status).toBe(429);
    expect(userFindUnique).toHaveBeenCalledTimes(10);
  });

  it("같은 IP로 30회를 넘기면 429", async () => {
    for (let i = 0; i < 30; i++) {
      await POST(req({ guestId: "nope", password: "x" }, "10.0.0.7"));
    }
    const blocked = await POST(req({ guestId: "guest_1234", password: "abcde" }, "10.0.0.7"));
    expect(blocked.status).toBe(429);
    expect(userFindUnique).not.toHaveBeenCalled();
  });
  describe("입장 링크(invite)", () => {
    const secret = "A".repeat(20) + "b_-" + "9".repeat(20);

    it("코드를 아이디·비밀값으로 나눠 합성 이메일 조회·비밀값 대조 후 쿠키 발급", async () => {
      userFindUnique.mockResolvedValue(activeGuest);
      verifyPassword.mockResolvedValue(true);
      userUpdate.mockResolvedValue({});
      const res = await POST(req({ invite: `guest_1234.${secret}` }));
      expect(res.status).toBe(200);
      expect(userFindUnique).toHaveBeenCalledWith({
        where: { email: "guest_1234@guest.nullstock.im" },
      });
      expect(verifyPassword).toHaveBeenCalledWith(secret, "hashed");
      expect(cookieSet).toHaveBeenCalledWith("token", "signed-jwt", expect.anything());
    });

    it("형식이 다른 코드는 DB를 보지 않고 401", async () => {
      const res = await POST(req({ invite: "guest_1234.short" }));
      expect(res.status).toBe(401);
      expect(userFindUnique).not.toHaveBeenCalled();
    });

    it("비밀값이 틀리면 401, 쿠키 없음", async () => {
      userFindUnique.mockResolvedValue(activeGuest);
      verifyPassword.mockResolvedValue(false);
      const res = await POST(req({ invite: `guest_1234.${secret}` }));
      expect(res.status).toBe(401);
      expect(cookieSet).not.toHaveBeenCalled();
    });

    it("같은 아이디에 틀린 비밀번호 10회가 쌓여도 링크 입장은 막히지 않는다", async () => {
      userFindUnique.mockResolvedValue(activeGuest);
      verifyPassword.mockResolvedValue(false);
      for (let i = 0; i < 10; i++) {
        await POST(req({ guestId: "guest_1234", password: "wrong" }, `10.0.1.${i}`));
      }
      verifyPassword.mockResolvedValue(true);
      userUpdate.mockResolvedValue({});
      const res = await POST(req({ invite: `guest_1234.${secret}` }, "10.0.2.1"));
      expect(res.status).toBe(200);
    });
  });
});
