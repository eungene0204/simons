-- 가상계좌 예약 주문 큐(2026-09-14) — 신호 후 N거래일 지연 체결(execution_delay_days>1)의 자동매매 대응.
-- additive: 새 테이블만 추가, 기존 데이터 무영향.
CREATE TABLE "VirtualScheduledOrder" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "strategyId" TEXT,
    "symbol" TEXT NOT NULL,
    "name" TEXT,
    "side" TEXT NOT NULL,
    "signalType" TEXT NOT NULL,
    "signalDate" TEXT NOT NULL,
    "delayDays" INTEGER NOT NULL,
    "reason" TEXT,
    "status" TEXT NOT NULL DEFAULT 'SCHEDULED',
    "resolution" TEXT,
    "orderId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "resolvedAt" TIMESTAMP(3),

    CONSTRAINT "VirtualScheduledOrder_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "VirtualScheduledOrder_accountId_status_idx" ON "VirtualScheduledOrder"("accountId", "status");

ALTER TABLE "VirtualScheduledOrder" ADD CONSTRAINT "VirtualScheduledOrder_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;
