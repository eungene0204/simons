-- 가상계좌 총 자산 시간별 스냅샷(2026-10-30) — 시간별 수익률 그래프.
-- additive: 새 테이블만 추가, 기존 데이터 무영향.
CREATE TABLE "VirtualAccountSnapshot" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "takenAt" TIMESTAMP(3) NOT NULL,
    "totalValue" DECIMAL(65,30) NOT NULL,
    "totalContributed" DECIMAL(65,30) NOT NULL,

    CONSTRAINT "VirtualAccountSnapshot_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "VirtualAccountSnapshot_accountId_takenAt_key" ON "VirtualAccountSnapshot"("accountId", "takenAt");

ALTER TABLE "VirtualAccountSnapshot" ADD CONSTRAINT "VirtualAccountSnapshot_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;
