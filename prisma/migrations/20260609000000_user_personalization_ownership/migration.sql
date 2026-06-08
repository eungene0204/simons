PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;

CREATE TABLE "new_Strategy" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "settings" TEXT NOT NULL,
    "strategyType" TEXT NOT NULL DEFAULT '기타',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "deletedAt" DATETIME,
    CONSTRAINT "Strategy_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_Strategy" (
    "id",
    "name",
    "description",
    "settings",
    "strategyType",
    "createdAt",
    "updatedAt",
    "deletedAt"
)
SELECT
    "id",
    "name",
    "description",
    "settings",
    "strategyType",
    "createdAt",
    "updatedAt",
    "deletedAt"
FROM "Strategy";
DROP TABLE "Strategy";
ALTER TABLE "new_Strategy" RENAME TO "Strategy";
CREATE INDEX "Strategy_userId_createdAt_idx" ON "Strategy"("userId", "createdAt");

CREATE TABLE "new_VirtualAccount" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "initialCash" REAL NOT NULL,
    "currentCash" REAL NOT NULL,
    "strategyId" TEXT,
    "strategyName" TEXT,
    "tradingMode" TEXT NOT NULL DEFAULT 'manual',
    "delistingPolicy" TEXT NOT NULL DEFAULT 'AUTO_LIQUIDATE',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "VirtualAccount_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_VirtualAccount" (
    "id",
    "name",
    "initialCash",
    "currentCash",
    "strategyId",
    "strategyName",
    "tradingMode",
    "delistingPolicy",
    "createdAt",
    "updatedAt"
)
SELECT
    "id",
    "name",
    "initialCash",
    "currentCash",
    "strategyId",
    "strategyName",
    "tradingMode",
    "delistingPolicy",
    "createdAt",
    "updatedAt"
FROM "VirtualAccount";
DROP TABLE "VirtualAccount";
ALTER TABLE "new_VirtualAccount" RENAME TO "VirtualAccount";
CREATE INDEX "VirtualAccount_userId_createdAt_idx" ON "VirtualAccount"("userId", "createdAt");

CREATE TABLE "new_WatchlistGroup" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "color" TEXT NOT NULL DEFAULT '#3B82F6',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "WatchlistGroup_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_WatchlistGroup" (
    "id",
    "name",
    "color",
    "createdAt"
)
SELECT
    "id",
    "name",
    "color",
    "createdAt"
FROM "WatchlistGroup";
DROP TABLE "WatchlistGroup";
ALTER TABLE "new_WatchlistGroup" RENAME TO "WatchlistGroup";
CREATE INDEX "WatchlistGroup_userId_createdAt_idx" ON "WatchlistGroup"("userId", "createdAt");

CREATE TABLE "new_WatchlistSymbol" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "addedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "groupId" TEXT,
    CONSTRAINT "WatchlistSymbol_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "WatchlistSymbol_groupId_fkey" FOREIGN KEY ("groupId") REFERENCES "WatchlistGroup" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_WatchlistSymbol" (
    "id",
    "symbol",
    "name",
    "addedAt",
    "groupId"
)
SELECT
    "id",
    "symbol",
    "name",
    "addedAt",
    "groupId"
FROM "WatchlistSymbol";
DROP TABLE "WatchlistSymbol";
ALTER TABLE "new_WatchlistSymbol" RENAME TO "WatchlistSymbol";
CREATE INDEX "WatchlistSymbol_userId_addedAt_idx" ON "WatchlistSymbol"("userId", "addedAt");
CREATE UNIQUE INDEX "WatchlistSymbol_userId_symbol_key" ON "WatchlistSymbol"("userId", "symbol");

PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
