-- CreateTable
CREATE TABLE "UserBacktestHistory" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER NOT NULL,
    "backtestHistoryId" TEXT NOT NULL,
    "savedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "UserBacktestHistory_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "UserBacktestHistory_backtestHistoryId_fkey" FOREIGN KEY ("backtestHistoryId") REFERENCES "BacktestHistory" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "UserBacktestHistory_userId_savedAt_idx" ON "UserBacktestHistory"("userId", "savedAt");

-- CreateIndex
CREATE UNIQUE INDEX "UserBacktestHistory_userId_backtestHistoryId_key" ON "UserBacktestHistory"("userId", "backtestHistoryId");

-- Backfill: 기존에 노출(isVisible)되던 백테스트 기록을 해당 전략 소유자의 목록으로 이관한다.
INSERT INTO "UserBacktestHistory" ("id", "userId", "backtestHistoryId", "savedAt")
SELECT lower(hex(randomblob(16))), s."userId", bh."id", bh."createdAt"
FROM "BacktestHistory" bh
JOIN "Strategy" s ON s."id" = bh."strategyId"
WHERE bh."isVisible" = 1 AND s."userId" IS NOT NULL;
