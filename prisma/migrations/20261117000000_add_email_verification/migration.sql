-- 이메일 인증번호 테이블을 마이그레이션 이력에 기록한다(2026-11-17).
-- 운영 DB에는 마이그레이션 없이 수동 CREATE로 먼저 생겼다(정의는 schema.prisma와 동일 — prisma migrate diff로 확인).
-- 이 파일이 없으면 다음 `prisma migrate dev`가 CREATE TABLE을 새로 만들어 운영 `migrate deploy`가
-- "already exists"로 멈춘다. IF NOT EXISTS라 운영에서는 아무것도 바꾸지 않고, CI·새 환경에는 테이블을 만든다.
CREATE TABLE IF NOT EXISTS "EmailVerification" (
    "email" TEXT NOT NULL,
    "codeHash" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "lastSentAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EmailVerification_pkey" PRIMARY KEY ("email")
);
