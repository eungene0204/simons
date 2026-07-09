-- NewsV2 tables (extracted from prisma diff)
-- Applied manually to avoid touching other unrelated drift in the diff.

PRAGMA busy_timeout=30000;

CREATE TABLE IF NOT EXISTS "NewsV2Article" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "normalizedTitle" TEXT NOT NULL,
    "summary" TEXT,
    "source" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "publishedAt" DATETIME NOT NULL,
    "sentiment" TEXT,
    "sentimentScore" REAL,
    "impactLevel" TEXT,
    "marketEffect" TEXT,
    "relatedSymbols" TEXT,
    "aiSummary" TEXT,
    "embedding" BLOB,
    "hash" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'analyzed',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS "NewsV2PriorityScore" (
    "symbol" TEXT NOT NULL PRIMARY KEY,
    "score" REAL NOT NULL DEFAULT 0,
    "tier" INTEGER NOT NULL DEFAULT 3,
    "lastCollected" DATETIME,
    "lastViewed" DATETIME,
    "viewCount24h" INTEGER NOT NULL DEFAULT 0,
    "watchlistCount" INTEGER NOT NULL DEFAULT 0,
    "searchCount24h" INTEGER NOT NULL DEFAULT 0,
    "volatility" REAL NOT NULL DEFAULT 0,
    "turnover" REAL NOT NULL DEFAULT 0,
    "aiImportance" REAL NOT NULL DEFAULT 0,
    "updatedAt" DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS "NewsV2CollectionStatus" (
    "symbol" TEXT NOT NULL PRIMARY KEY,
    "status" TEXT NOT NULL DEFAULT 'NOT_COLLECTED',
    "lastSuccessAt" DATETIME,
    "lastAttemptAt" DATETIME,
    "lastError" TEXT,
    "attemptCount" INTEGER NOT NULL DEFAULT 0,
    "inFlightJobId" TEXT,
    "updatedAt" DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS "NewsV2IngestionLog" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "jobId" TEXT,
    "startedAt" DATETIME NOT NULL,
    "finishedAt" DATETIME,
    "fetched" INTEGER NOT NULL DEFAULT 0,
    "deduped" INTEGER NOT NULL DEFAULT 0,
    "inserted" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL,
    "error" TEXT
);

CREATE INDEX IF NOT EXISTS "NewsV2Article_symbol_publishedAt_idx" ON "NewsV2Article"("symbol", "publishedAt");
CREATE INDEX IF NOT EXISTS "NewsV2Article_hash_idx" ON "NewsV2Article"("hash");
CREATE INDEX IF NOT EXISTS "NewsV2Article_publishedAt_idx" ON "NewsV2Article"("publishedAt");
CREATE UNIQUE INDEX IF NOT EXISTS "NewsV2Article_symbol_hash_key" ON "NewsV2Article"("symbol", "hash");
CREATE INDEX IF NOT EXISTS "NewsV2PriorityScore_tier_score_idx" ON "NewsV2PriorityScore"("tier", "score");
CREATE INDEX IF NOT EXISTS "NewsV2IngestionLog_symbol_startedAt_idx" ON "NewsV2IngestionLog"("symbol", "startedAt");
