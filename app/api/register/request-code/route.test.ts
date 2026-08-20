// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { hashVerificationCode } from "@/lib/server/email-verification";

// 인증번호 발송 라우트의 보안 계약:
// - 이미 가입된 이메일이어도 응답(200·메시지)이 미가입과 동일해야 한다(계정 열거 방지)
// - 코드 원문이 아니라 SHA-256 해시가 저장돼야 한다
// - 레이트리밋 초과는 429

const userFindUnique = vi.fn();
const verificationUpsert = vi.fn();
const sendVerificationEmail = vi.fn();
const sendAlreadyRegisteredEmail = vi.fn();
const consumeRateLimit = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { findUnique: (...a) => userFindUnique(...a) },
    emailVerification: { upsert: (...a) => verificationUpsert(...a) },
  },
}));

vi.mock("@/lib/server/mailer", () => ({
  sendVerificationEmail: (...a) => sendVerificationEmail(...a),
  sendAlreadyRegisteredEmail: (...a) => sendAlreadyRegisteredEmail(...a),
}));

vi.mock("@/lib/server/rate-limit", () => ({
  consumeRateLimit: (...a) => consumeRateLimit(...a),
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

describe("/api/register/request-code", () => {
  it("이메일 형식이 아니면 400", async () => {
    const res = await POST(req({ email: "not-an-email" }));
    expect(res.status).toBe(400);
    expect(verificationUpsert).not.toHaveBeenCalled();
  });

  it("미가입 이메일이면 코드 해시를 upsert하고 인증 메일을 보낸다", async () => {
    userFindUnique.mockResolvedValue(null);
    verificationUpsert.mockResolvedValue({});
    sendVerificationEmail.mockResolvedValue(undefined);

    const res = await POST(req({ email: "New.User@Example.com " }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.message).toBe("인증번호를 발송했습니다. 메일함을 확인해주세요.");

    // 이메일은 정규화(trim + 소문자)돼야 한다
    const upsertArg = verificationUpsert.mock.calls[0][0];
    expect(upsertArg.where.email).toBe("new.user@example.com");

    // 저장된 값은 코드 원문이 아니라 해시여야 한다
    const [sentTo, sentCode] = sendVerificationEmail.mock.calls[0];
    expect(sentTo).toBe("new.user@example.com");
    expect(sentCode).toMatch(/^\d{6}$/);
    expect(upsertArg.create.codeHash).toBe(hashVerificationCode(sentCode));
    expect(upsertArg.create.codeHash).not.toBe(sentCode);
  });

  it("가입된 이메일도 응답이 동일하고(200·같은 메시지) 코드가 만들어지지 않는다", async () => {
    userFindUnique.mockResolvedValue({ id: 1, email: "user@example.com" });
    sendAlreadyRegisteredEmail.mockResolvedValue(undefined);

    const res = await POST(req({ email: "user@example.com" }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.message).toBe("인증번호를 발송했습니다. 메일함을 확인해주세요.");
    expect(verificationUpsert).not.toHaveBeenCalled();
    expect(sendVerificationEmail).not.toHaveBeenCalled();
    expect(sendAlreadyRegisteredEmail).toHaveBeenCalledWith("user@example.com");
  });

  it("레이트리밋 초과면 429이고 DB를 건드리지 않는다", async () => {
    consumeRateLimit.mockReturnValue(false);

    const res = await POST(req({ email: "user@example.com" }));

    expect(res.status).toBe(429);
    expect(userFindUnique).not.toHaveBeenCalled();
    expect(verificationUpsert).not.toHaveBeenCalled();
  });

  it("메일 발송 실패는 500으로 드러난다", async () => {
    userFindUnique.mockResolvedValue(null);
    verificationUpsert.mockResolvedValue({});
    sendVerificationEmail.mockRejectedValue(new Error("SMTP down"));

    const res = await POST(req({ email: "user@example.com" }));

    expect(res.status).toBe(500);
  });
});
