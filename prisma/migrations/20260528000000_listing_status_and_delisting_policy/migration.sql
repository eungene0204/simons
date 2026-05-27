-- AlterTable: Add listing status fields to Stock
ALTER TABLE "Stock" ADD COLUMN "listingStatus" TEXT NOT NULL DEFAULT 'NORMAL';
ALTER TABLE "Stock" ADD COLUMN "suspensionReason" TEXT;
ALTER TABLE "Stock" ADD COLUMN "delistingDate" TEXT;
ALTER TABLE "Stock" ADD COLUMN "lastTradableDate" TEXT;
ALTER TABLE "Stock" ADD COLUMN "riskFlags" TEXT;
ALTER TABLE "Stock" ADD COLUMN "statusUpdatedAt" DATETIME;

-- CreateIndex
CREATE INDEX "Stock_listingStatus_idx" ON "Stock"("listingStatus");

-- AlterTable: Add delistingPolicy to VirtualAccount
ALTER TABLE "VirtualAccount" ADD COLUMN "delistingPolicy" TEXT NOT NULL DEFAULT 'AUTO_LIQUIDATE';

-- CreateTable: DelistingAuditLog
CREATE TABLE "DelistingAuditLog" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "actionType" TEXT NOT NULL,
    "previousStatus" TEXT,
    "newStatus" TEXT,
    "quantity" INTEGER,
    "executionPrice" REAL,
    "reason" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DelistingAuditLog_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "DelistingAuditLog_accountId_createdAt_idx" ON "DelistingAuditLog"("accountId", "createdAt");

-- CreateIndex
CREATE INDEX "DelistingAuditLog_symbol_createdAt_idx" ON "DelistingAuditLog"("symbol", "createdAt");
