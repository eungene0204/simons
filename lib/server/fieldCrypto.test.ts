import { afterEach, describe, expect, it, vi } from "vitest";
import {
  FieldCryptoError,
  assertFieldCryptoReady,
  decryptField,
  encryptField,
  isEncryptedField,
} from "./fieldCrypto";

const OTHER_KEY = Buffer.alloc(32, 9).toString("base64");

describe("lib/server/fieldCrypto", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("암호화한 값은 원문을 담지 않고 왕복한다", () => {
    const stored = encryptField("bkey_20260911_abcdef");

    expect(stored).not.toContain("bkey_20260911_abcdef");
    expect(isEncryptedField(stored)).toBe(true);
    expect(decryptField(stored)).toBe("bkey_20260911_abcdef");
  });

  it("같은 값도 매번 다른 암호문이 된다(IV 재사용 없음)", () => {
    expect(encryptField("same")).not.toBe(encryptField("same"));
  });

  it("다른 키로는 복호화되지 않는다", () => {
    const stored = encryptField("bkey_1");
    vi.stubEnv("FIELD_ENCRYPTION_KEY", OTHER_KEY);

    expect(() => decryptField(stored)).toThrow();
  });

  it("암호문이 위조되면 인증 태그 검증에서 실패한다", () => {
    const stored = encryptField("bkey_1");
    const forged = `${stored.slice(0, -4)}AAAA`;

    expect(() => decryptField(forged)).toThrow();
  });

  // 키가 없다고 평문으로 저장하는 폴백은 두지 않는다.
  it("키가 없으면 암호화도 사전 점검도 거부한다", () => {
    vi.stubEnv("FIELD_ENCRYPTION_KEY", "");

    expect(() => assertFieldCryptoReady()).toThrow(FieldCryptoError);
    expect(() => encryptField("bkey_1")).toThrow(/FIELD_ENCRYPTION_KEY is not set/);
  });

  it("키 길이가 32바이트가 아니면 거부한다", () => {
    vi.stubEnv("FIELD_ENCRYPTION_KEY", Buffer.alloc(16, 1).toString("base64"));

    expect(() => encryptField("bkey_1")).toThrow(/32 bytes/);
  });

  // 백필 이전에 저장된 평문 행이 있어도 구독 청구는 끊기지 않아야 한다.
  it("접두사가 없는 레거시 평문은 경고와 함께 그대로 돌려준다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(decryptField("legacy-plaintext-key")).toBe("legacy-plaintext-key");
    expect(isEncryptedField("legacy-plaintext-key")).toBe(false);
    expect(warn).toHaveBeenCalled();
  });
});
