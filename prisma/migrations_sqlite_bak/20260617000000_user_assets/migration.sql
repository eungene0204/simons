CREATE TABLE "UserAsset" (
    "userId" INTEGER NOT NULL PRIMARY KEY,
    "availableCash" DECIMAL NOT NULL DEFAULT 10000000,
    "initialGrantAmount" DECIMAL NOT NULL DEFAULT 10000000,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "UserAsset_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE "AssetLedger" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER NOT NULL,
    "accountId" TEXT,
    "type" TEXT NOT NULL,
    "amount" DECIMAL NOT NULL,
    "balanceAfter" DECIMAL NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AssetLedger_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "AssetLedger_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX "AssetLedger_userId_createdAt_idx" ON "AssetLedger"("userId", "createdAt");
CREATE INDEX "AssetLedger_accountId_createdAt_idx" ON "AssetLedger"("accountId", "createdAt");
CREATE INDEX "AssetLedger_type_idx" ON "AssetLedger"("type");

ALTER TABLE "VirtualAccount" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE "VirtualAccount" ADD COLUMN "closedAt" DATETIME;
CREATE INDEX "VirtualAccount_userId_status_idx" ON "VirtualAccount"("userId", "status");
