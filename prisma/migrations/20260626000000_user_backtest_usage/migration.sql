-- 월 백테스트 사용량 추적 필드 (달력 월 기준 초기화)
ALTER TABLE "User" ADD COLUMN "backtestUsageMonth" TEXT;
ALTER TABLE "User" ADD COLUMN "backtestCountThisMonth" INTEGER NOT NULL DEFAULT 0;
