PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;

CREATE TABLE "new_VirtualAccount" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "initialCash" DECIMAL NOT NULL,
    "currentCash" DECIMAL NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "strategyId" TEXT,
    "strategyName" TEXT,
    "tradingMode" TEXT NOT NULL DEFAULT 'manual',
    "delistingPolicy" TEXT NOT NULL DEFAULT 'AUTO_LIQUIDATE',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "closedAt" DATETIME,
    CONSTRAINT "VirtualAccount_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_VirtualAccount" (
    "id", "userId", "name", "initialCash", "currentCash", "status",
    "strategyId", "strategyName", "tradingMode", "delistingPolicy",
    "createdAt", "updatedAt", "closedAt"
)
SELECT
    "id", "userId", "name", "initialCash", "currentCash", "status",
    "strategyId", "strategyName", "tradingMode", "delistingPolicy",
    "createdAt", "updatedAt", "closedAt"
FROM "VirtualAccount";
DROP TABLE "VirtualAccount";
ALTER TABLE "new_VirtualAccount" RENAME TO "VirtualAccount";
CREATE INDEX "VirtualAccount_userId_createdAt_idx" ON "VirtualAccount"("userId", "createdAt");
CREATE INDEX "VirtualAccount_userId_status_idx" ON "VirtualAccount"("userId", "status");

CREATE TABLE "new_VirtualOrder" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT,
    "side" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "price" DECIMAL NOT NULL,
    "filledPrice" DECIMAL,
    "status" TEXT NOT NULL,
    "filledAt" DATETIME,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "avgBuyPrice" DECIMAL,
    "fee" DECIMAL,
    "realizedPnl" DECIMAL,
    "tax" DECIMAL,
    CONSTRAINT "VirtualOrder_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO "new_VirtualOrder" (
    "id", "accountId", "symbol", "name", "side", "type", "quantity",
    "price", "filledPrice", "status", "filledAt", "createdAt",
    "avgBuyPrice", "fee", "realizedPnl", "tax"
)
SELECT
    "id", "accountId", "symbol", "name", "side", "type", "quantity",
    "price", "filledPrice", "status", "filledAt", "createdAt",
    "avgBuyPrice", "fee", "realizedPnl", "tax"
FROM "VirtualOrder";
DROP TABLE "VirtualOrder";
ALTER TABLE "new_VirtualOrder" RENAME TO "VirtualOrder";

CREATE TABLE "new_VirtualPosition" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "avgPrice" DECIMAL NOT NULL,
    "currentPrice" DECIMAL,
    "openedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "peakPrice" DECIMAL,
    CONSTRAINT "VirtualPosition_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO "new_VirtualPosition" (
    "id", "accountId", "symbol", "name", "quantity", "avgPrice",
    "currentPrice", "openedAt", "updatedAt", "peakPrice"
)
SELECT
    "id", "accountId", "symbol", "name", "quantity", "avgPrice",
    "currentPrice", "openedAt", "updatedAt", "peakPrice"
FROM "VirtualPosition";
DROP TABLE "VirtualPosition";
ALTER TABLE "new_VirtualPosition" RENAME TO "VirtualPosition";
CREATE UNIQUE INDEX "VirtualPosition_accountId_symbol_key" ON "VirtualPosition"("accountId", "symbol");

PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
