-- 수익 자동화(2026-11-26): 한도 도달 기록·가입 유입 경로·저장 전략 월간 리포트 수신 설정.
-- 전부 추가(additive) 변경이다 — 기존 행·쿼리에 영향이 없다.
SET lock_timeout = '5s';

ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "signupUtmSource" TEXT;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "signupUtmMedium" TEXT;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "signupUtmCampaign" TEXT;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "strategyReportOptIn" BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "strategyReportLastSentKey" TEXT;

CREATE TABLE IF NOT EXISTS "PlanLimitHit" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "code" TEXT NOT NULL,
    "planTier" TEXT NOT NULL,
    "periodKey" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PlanLimitHit_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "PlanLimitHit_userId_code_periodKey_key" ON "PlanLimitHit"("userId", "code", "periodKey");
CREATE INDEX IF NOT EXISTS "PlanLimitHit_createdAt_idx" ON "PlanLimitHit"("createdAt");

DO $$ BEGIN
  ALTER TABLE "PlanLimitHit" ADD CONSTRAINT "PlanLimitHit_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 새 테이블은 20261117030000_enable_rls_public의 일괄 적용 대상이 아니다 — 여기서 함께 켠다.
ALTER TABLE "PlanLimitHit" ENABLE ROW LEVEL SECURITY;

RESET lock_timeout;
