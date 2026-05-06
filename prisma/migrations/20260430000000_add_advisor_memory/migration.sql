CREATE TABLE "BacktestRun" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "strategyId" TEXT NOT NULL,
    "market" TEXT,
    "universe" TEXT,
    "timeframe" TEXT NOT NULL DEFAULT '1d',
    "startDate" TEXT,
    "endDate" TEXT,
    "initialCapital" REAL NOT NULL,
    "commissionBps" REAL NOT NULL DEFAULT 0,
    "slippageBps" REAL NOT NULL DEFAULT 0,
    "liquidityPolicy" TEXT,
    "universeSnapshotHash" TEXT,
    "resultMetrics" TEXT NOT NULL,
    "monthlyReturns" TEXT,
    "rollingMetrics" TEXT,
    "oosMetrics" TEXT,
    "walkForwardResult" TEXT,
    "tradeStats" TEXT,
    "status" TEXT NOT NULL DEFAULT 'completed',
    "cacheKey" TEXT NOT NULL,
    "hitCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BacktestRun_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE "StrategyEmbedding" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "strategyId" TEXT NOT NULL,
    "embeddingType" TEXT NOT NULL,
    "sourceText" TEXT NOT NULL,
    "vector" BLOB,
    "sparseTokens" TEXT,
    "modelName" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "StrategyEmbedding_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE "AdviceExperience" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "strategyId" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "market" TEXT,
    "universe" TEXT,
    "initialCapital" REAL NOT NULL,
    "timeframe" TEXT NOT NULL DEFAULT '1d',
    "userPrompt" TEXT NOT NULL,
    "strategySummary" TEXT,
    "strategyDsl" TEXT NOT NULL,
    "canonicalDsl" TEXT NOT NULL,
    "strategyHash" TEXT NOT NULL,
    "similarStrategyIds" TEXT NOT NULL,
    "retrievedCases" TEXT NOT NULL,
    "agentAdvice" TEXT NOT NULL,
    "beforeBacktest" TEXT NOT NULL,
    "afterBacktest" TEXT,
    "evaluation" TEXT NOT NULL,
    "lesson" TEXT NOT NULL,
    "confidence" TEXT NOT NULL,
    "dataCoverage" TEXT,
    CONSTRAINT "AdviceExperience_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "BacktestRun_cacheKey_key" ON "BacktestRun"("cacheKey");
CREATE INDEX "BacktestRun_strategyId_idx" ON "BacktestRun"("strategyId");
CREATE INDEX "BacktestRun_strategyId_createdAt_idx" ON "BacktestRun"("strategyId", "createdAt");
CREATE INDEX "StrategyEmbedding_strategyId_idx" ON "StrategyEmbedding"("strategyId");
CREATE INDEX "StrategyEmbedding_embeddingType_idx" ON "StrategyEmbedding"("embeddingType");
CREATE INDEX "AdviceExperience_strategyId_idx" ON "AdviceExperience"("strategyId");
CREATE INDEX "AdviceExperience_market_universe_idx" ON "AdviceExperience"("market", "universe");
CREATE INDEX "AdviceExperience_confidence_idx" ON "AdviceExperience"("confidence");
