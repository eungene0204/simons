-- CreateTable
CREATE TABLE "BatchRun" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "totalPrompts" INTEGER NOT NULL,
    "completedCount" INTEGER NOT NULL DEFAULT 0,
    "failedCount" INTEGER NOT NULL DEFAULT 0,
    "skippedCount" INTEGER NOT NULL DEFAULT 0,
    "rankingSnapshot" TEXT NOT NULL,
    "logs" TEXT
);

-- CreateTable
CREATE TABLE "BatchRunCandidate" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "runId" TEXT NOT NULL,
    "strategyId" TEXT,
    "prompt" TEXT NOT NULL,
    "strategyName" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "errorMessage" TEXT,
    "metrics" TEXT,
    "rank" INTEGER,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BatchRunCandidate_runId_fkey" FOREIGN KEY ("runId") REFERENCES "BatchRun" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "BatchRunCandidate_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_BacktestHistory" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "strategyId" TEXT,
    "strategyName" TEXT NOT NULL,
    "universe" TEXT NOT NULL,
    "conditions" TEXT NOT NULL,
    "metrics" TEXT NOT NULL,
    "result" TEXT,
    "cacheKey" TEXT,
    "isVisible" BOOLEAN NOT NULL DEFAULT false,
    "hitCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BacktestHistory_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_BacktestHistory" ("cacheKey", "conditions", "createdAt", "hitCount", "id", "isVisible", "metrics", "result", "strategyName", "universe")
SELECT "cacheKey", "conditions", "createdAt", "hitCount", "id", "isVisible", "metrics", "result", "strategyName", "universe" FROM "BacktestHistory";
DROP TABLE "BacktestHistory";
ALTER TABLE "new_BacktestHistory" RENAME TO "BacktestHistory";
CREATE UNIQUE INDEX "BacktestHistory_cacheKey_key" ON "BacktestHistory"("cacheKey");
CREATE INDEX "BacktestHistory_strategyId_createdAt_idx" ON "BacktestHistory"("strategyId", "createdAt");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

-- CreateIndex
CREATE INDEX "BatchRun_createdAt_idx" ON "BatchRun"("createdAt");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_runId_createdAt_idx" ON "BatchRunCandidate"("runId", "createdAt");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_runId_status_idx" ON "BatchRunCandidate"("runId", "status");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_strategyId_idx" ON "BatchRunCandidate"("strategyId");

-- CreateIndex
CREATE INDEX "BacktestResult_strategyId_createdAt_idx" ON "BacktestResult"("strategyId", "createdAt");
