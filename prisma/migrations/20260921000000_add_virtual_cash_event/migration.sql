-- 가상계좌 정액 적립식(2026-09-21) — 정기 납입 기록과 총 납입액.
-- additive: 새 컬럼 2개(기본값 0 / NULL)와 새 테이블만 추가, 기존 데이터 무영향.
ALTER TABLE "VirtualAccount" ADD COLUMN "contributedCash" DECIMAL(65,30) NOT NULL DEFAULT 0;
ALTER TABLE "VirtualAccount" ADD COLUMN "contributionCap" DECIMAL(65,30);

CREATE TABLE "VirtualCashEvent" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "amount" DECIMAL(65,30) NOT NULL,
    "balanceAfter" DECIMAL(65,30) NOT NULL,
    "date" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "VirtualCashEvent_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "VirtualCashEvent_accountId_date_key" ON "VirtualCashEvent"("accountId", "date");

CREATE INDEX "VirtualCashEvent_accountId_createdAt_idx" ON "VirtualCashEvent"("accountId", "createdAt");

ALTER TABLE "VirtualCashEvent" ADD CONSTRAINT "VirtualCashEvent_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;
