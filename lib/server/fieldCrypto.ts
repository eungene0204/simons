import crypto from "crypto";

/**
 * 저장 필드 암호화 — 되돌려 써야 하는 자격증명 전용(AES-256-GCM).
 *
 * 비밀번호·인증번호처럼 대조만 하면 되는 값은 단방향 해시로 끝낸다(bcrypt/SHA-256).
 * 반대로 토스 자동결제 빌링키는 매달 원문 그대로 토스에 보내야 하므로 해시할 수 없고,
 * 평문으로 두면 DB 사본 하나가 곧 카드 청구 가능으로 이어진다. 그 간극을 메우는 계층이다.
 *
 * 저장 형식: `enc:v1:<iv>:<tag>:<ciphertext>` (각 조각 base64)
 * - 접두사가 있어야만 암호문으로 인정한다 — 평문 레거시 행과 구분하고, 키를 교체할 때
 *   버전으로 갈래를 나눈다.
 * - GCM 인증 태그를 함께 저장해 위조된 암호문은 복호화 단계에서 실패한다.
 *
 * 키: `FIELD_ENCRYPTION_KEY`(base64, 32바이트). 없으면 암호화도 복호화도 하지 않고
 * 예외를 던진다 — 키가 없다고 평문으로 저장하는 폴백은 두지 않는다.
 */

const PREFIX = "enc:v1:";
const ALGORITHM = "aes-256-gcm";
const IV_BYTES = 12; // GCM 권장 길이
const KEY_BYTES = 32;

export class FieldCryptoError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FieldCryptoError";
  }
}

function loadKey(): Buffer {
  const raw = process.env.FIELD_ENCRYPTION_KEY;
  if (!raw) {
    throw new FieldCryptoError(
      "FIELD_ENCRYPTION_KEY is not set. Refusing to store or read an encrypted credential."
    );
  }
  const key = Buffer.from(raw, "base64");
  if (key.length !== KEY_BYTES) {
    throw new FieldCryptoError(
      `FIELD_ENCRYPTION_KEY must decode to ${KEY_BYTES} bytes (got ${key.length}).`
    );
  }
  return key;
}

/** 키 설정 여부만 확인한다 — 돈이 움직이기 전에 미리 검사하는 용도. */
export function assertFieldCryptoReady(): void {
  loadKey();
}

export function isEncryptedField(value: string): boolean {
  return value.startsWith(PREFIX);
}

export function encryptField(plaintext: string): string {
  if (!plaintext) {
    throw new FieldCryptoError("Cannot encrypt an empty value.");
  }
  const iv = crypto.randomBytes(IV_BYTES);
  const cipher = crypto.createCipheriv(ALGORITHM, loadKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${PREFIX}${iv.toString("base64")}:${tag.toString("base64")}:${ciphertext.toString("base64")}`;
}

/**
 * 저장값을 원문으로 되돌린다.
 *
 * 접두사가 없는 값은 암호화 도입 이전에 저장된 평문이므로 그대로 돌려준다(구독 청구가
 * 끊기지 않게 하는 한시 호환). 백필(`scripts/encrypt-billing-keys.ts`)이 돌면 이 경로로
 * 들어오는 값은 없어야 하며, 남아 있으면 경고를 남긴다.
 */
export function decryptField(stored: string): string {
  if (!isEncryptedField(stored)) {
    console.warn("[fieldCrypto] 평문으로 저장된 자격증명을 읽었다 — 백필이 필요하다.");
    return stored;
  }

  const [ivB64, tagB64, dataB64] = stored.slice(PREFIX.length).split(":");
  if (!ivB64 || !tagB64 || !dataB64) {
    throw new FieldCryptoError("Malformed encrypted field.");
  }

  const decipher = crypto.createDecipheriv(
    ALGORITHM,
    loadKey(),
    Buffer.from(ivB64, "base64")
  );
  decipher.setAuthTag(Buffer.from(tagB64, "base64"));
  return Buffer.concat([
    decipher.update(Buffer.from(dataB64, "base64")),
    decipher.final(),
  ]).toString("utf8");
}
