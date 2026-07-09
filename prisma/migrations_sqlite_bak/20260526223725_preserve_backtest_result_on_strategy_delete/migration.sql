-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;

CREATE TABLE "new_BacktestResult" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "strategyId" TEXT,
    "stockId" INTEGER,
    "summary" TEXT NOT NULL,
    "trades" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BacktestResult_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "BacktestResult_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

INSERT INTO "new_BacktestResult" ("createdAt", "id", "stockId", "strategyId", "summary", "trades")
SELECT "createdAt", "id", "stockId", "strategyId", "summary", "trades"
FROM "BacktestResult";

DROP TABLE "BacktestResult";
ALTER TABLE "new_BacktestResult" RENAME TO "BacktestResult";

CREATE INDEX "BacktestResult_strategyId_createdAt_idx" ON "BacktestResult"("strategyId", "createdAt");

PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
