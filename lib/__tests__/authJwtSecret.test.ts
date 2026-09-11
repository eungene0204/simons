import { afterEach, describe, expect, it, vi } from "vitest";

async function loadAuth() {
  vi.resetModules();
  return import("@/lib/auth");
}

describe("lib/auth JWT_SECRET", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  // 미설정을 조용히 기본 키로 대체하면 누구나 임의 userId 토큰을 위조할 수 있다.
  it("운영에서 JWT_SECRET이 없으면 모듈 로드가 실패한다", async () => {
    vi.stubEnv("JWT_SECRET", "");
    vi.stubEnv("NODE_ENV", "production");

    await expect(loadAuth()).rejects.toThrow(/JWT_SECRET is not set/);
  });

  it("설정돼 있으면 그 키로 서명하고 검증한다", async () => {
    vi.stubEnv("JWT_SECRET", "unit-test-secret");
    vi.stubEnv("NODE_ENV", "production");

    const { generateToken, verifyToken } = await loadAuth();

    expect(verifyToken(generateToken(42))).toMatchObject({ userId: 42 });
  });

  it("다른 키로 서명된 토큰은 받아들이지 않는다", async () => {
    vi.stubEnv("JWT_SECRET", "key-a");
    const signer = await loadAuth();
    const token = signer.generateToken(42);

    vi.stubEnv("JWT_SECRET", "key-b");
    const verifier = await loadAuth();

    expect(verifier.verifyToken(token)).toBeNull();
  });
});
