// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { hashVerificationCode } from "@/lib/server/email-verification";

// 가입 라우트의 보안 계약:
// - 유효한 인증번호 없이는 계정이 생기지 않는다(이메일 소유 증명)
// - 잘못된 코드는 시도 횟수를 누적하고, 상한(5회) 도달 시 거부한다
// - 비밀번호 정책(8자+영문+숫자) 미달은 400
// - 성공 시 인증 행을 지우고 로그인 쿠키를 발급한다(자동 로그인)

const userFindUnique = vi.fn();
const userCreate = vi.fn();
const userUpdate = vi.fn();
const verificationFindUnique = vi.fn();
const verificationUpdate = vi.fn();
const verificationDeleteMany = vi.fn();
const ensureUserBootstrap = vi.fn();
const consumeRateLimit = vi.fn();
const cookieSet = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      create: (...a) => userCreate(...a),
      update: (...a) => userUpdate(...a),
    },
    emailVerification: {
      findUnique: (...a) => verificationFindUnique(...a),
      update: (...a) => verificationUpdate(...a),
      deleteMany: (...a) => verificationDeleteMany(...a),
    },
  },
}));

vi.mock("@/lib/auth", () => ({
  generateToken: () => "signed-jwt",
  hashPassword: async () => "hashed",
}));

vi.mock("@/lib/get-user", () => ({
  ensureUserBootstrap: (...a) => ensureUserBootstrap(...a),
}));

vi.mock("@/lib/server/rate-limit", () => ({
  consumeRateLimit: (...a) => consumeRateLimit(...a),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({ set: (...a) => cookieSet(...a) }),
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  consumeRateLimit.mockReturnValue(true);
  POST = (await import("./route")).POST;
});

function req(body, headers = {}) {
  return {
    json: async () => body,
    headers: { get: (key) => headers[key] ?? null },
  };
}

const validBody = {
  name: "Tester",
  email: "user@example.com",
  password: "abcdef12",
  code: "123456",
  termsAgreed: true,
};

function validVerificationRow(overrides = {}) {
  return {
    email: "user@example.com",
    codeHash: hashVerificationCode("123456"),
    expiresAt: new Date(Date.now() + 5 * 60 * 1000),
    attempts: 0,
    ...overrides,
  };
}

describe("/api/register", () => {
  it("비밀번호 정책 미달(숫자 없음)은 400이고 계정이 생기지 않는다", async () => {
    const res = await POST(req({ ...validBody, password: "abcdefgh" }));
    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("약관 미동의는 400", async () => {
    const res = await POST(req({ ...validBody, termsAgreed: false }));
    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("인증번호가 발송된 적 없으면 400", async () => {
    verificationFindUnique.mockResolvedValue(null);
    const res = await POST(req(validBody));
    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("만료된 인증번호는 400", async () => {
    verificationFindUnique.mockResolvedValue(
      validVerificationRow({ expiresAt: new Date(Date.now() - 1000) })
    );
    const res = await POST(req(validBody));
    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("잘못된 코드는 시도 횟수를 누적하고 400", async () => {
    verificationFindUnique.mockResolvedValue(validVerificationRow());
    verificationUpdate.mockResolvedValue({});

    const res = await POST(req({ ...validBody, code: "000000" }));

    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
    expect(verificationUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { email: "user@example.com" },
        data: { attempts: { increment: 1 } },
      })
    );
  });

  it("시도 상한(5회) 도달 후에는 올바른 코드여도 거부한다(무차별 대입 차단)", async () => {
    verificationFindUnique.mockResolvedValue(validVerificationRow({ attempts: 5 }));

    const res = await POST(req(validBody));

    expect(res.status).toBe(400);
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("올바른 코드면 계정 생성 + 인증 행 삭제 + 로그인 쿠키 발급(201)", async () => {
    verificationFindUnique.mockResolvedValue(validVerificationRow());
    userFindUnique.mockResolvedValue(null);
    userCreate.mockResolvedValue({ id: 7, email: "user@example.com", name: "Tester" });
    verificationDeleteMany.mockResolvedValue({});
    ensureUserBootstrap.mockResolvedValue(undefined);
    userUpdate.mockResolvedValue({});

    const res = await POST(req(validBody));
    const data = await res.json();

    expect(res.status).toBe(201);
    expect(data.user.id).toBe(7);
    // 비밀번호는 해시로 저장된다
    expect(userCreate.mock.calls[0][0].data.password).toBe("hashed");
    expect(verificationDeleteMany).toHaveBeenCalledWith({
      where: { email: "user@example.com" },
    });
    expect(cookieSet).toHaveBeenCalledWith(
      "token",
      "signed-jwt",
      expect.objectContaining({ httpOnly: true, sameSite: "lax" })
    );
  });

  it("인증을 통과했지만 이미 가입된 이메일이면 400", async () => {
    verificationFindUnique.mockResolvedValue(validVerificationRow());
    userFindUnique.mockResolvedValue({ id: 1, email: "user@example.com" });

    const res = await POST(req(validBody));
    const data = await res.json();

    expect(res.status).toBe(400);
    expect(data.error).toBe("이미 가입된 이메일입니다.");
    expect(userCreate).not.toHaveBeenCalled();
  });

  it("인증번호 단계 off(EMAIL_SIGNUP_VERIFICATION=off)면 code 없이 가입된다", async () => {
    vi.stubEnv("EMAIL_SIGNUP_VERIFICATION", "off");
    try {
      userFindUnique.mockResolvedValue(null);
      userCreate.mockResolvedValue({ id: 9, email: "user@example.com", name: "Tester" });
      verificationDeleteMany.mockResolvedValue({});
      ensureUserBootstrap.mockResolvedValue(undefined);
      userUpdate.mockResolvedValue({});

      const { code: _omitted, ...bodyWithoutCode } = validBody;
      const res = await POST(req(bodyWithoutCode));
      const data = await res.json();

      expect(res.status).toBe(201);
      expect(data.user.id).toBe(9);
      // 인증 행 조회 자체를 하지 않는다
      expect(verificationFindUnique).not.toHaveBeenCalled();
      expect(cookieSet).toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("인증번호 단계 off여도 비밀번호 정책은 그대로 강제된다", async () => {
    vi.stubEnv("EMAIL_SIGNUP_VERIFICATION", "off");
    try {
      const res = await POST(req({ ...validBody, code: undefined, password: "short1" }));
      expect(res.status).toBe(400);
      expect(userCreate).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("킬 스위치(EMAIL_SIGNUP_ENABLED=off)면 404이고 계정이 생기지 않는다", async () => {
    vi.stubEnv("EMAIL_SIGNUP_ENABLED", "off");
    try {
      const res = await POST(req(validBody));
      expect(res.status).toBe(404);
      expect(verificationFindUnique).not.toHaveBeenCalled();
      expect(userCreate).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("레이트리밋 초과면 429", async () => {
    consumeRateLimit.mockReturnValue(false);
    const res = await POST(req(validBody));
    expect(res.status).toBe(429);
    expect(verificationFindUnique).not.toHaveBeenCalled();
  });
});
