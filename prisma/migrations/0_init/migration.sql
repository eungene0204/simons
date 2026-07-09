-- CreateTable
CREATE TABLE "BacktestHistory" (
    "id" TEXT NOT NULL,
    "strategyId" TEXT,
    "strategyName" TEXT NOT NULL,
    "prompt" TEXT,
    "universe" TEXT NOT NULL,
    "conditions" TEXT NOT NULL,
    "metrics" TEXT NOT NULL,
    "result" TEXT,
    "cacheKey" TEXT,
    "isVisible" BOOLEAN NOT NULL DEFAULT false,
    "hitCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BacktestHistory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UserBacktestHistory" (
    "id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "backtestHistoryId" TEXT NOT NULL,
    "savedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "UserBacktestHistory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BacktestResult" (
    "id" TEXT NOT NULL,
    "strategyId" TEXT,
    "stockId" INTEGER,
    "summary" TEXT NOT NULL,
    "trades" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BacktestResult_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SavedValidation" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "modelType" TEXT NOT NULL,
    "strategyName" TEXT NOT NULL,
    "prompt" TEXT,
    "cacheKey" TEXT,
    "settings" TEXT NOT NULL,
    "result" TEXT NOT NULL,
    "summary" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SavedValidation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Stock" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT,
    "market" TEXT,
    "sector" TEXT,
    "industry" TEXT,
    "description" TEXT,
    "listingDate" TEXT,
    "profileSource" TEXT,
    "profileUpdatedAt" TIMESTAMP(3),
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "listingStatus" TEXT NOT NULL DEFAULT 'NORMAL',
    "suspensionReason" TEXT,
    "delistingDate" TEXT,
    "lastTradableDate" TEXT,
    "riskFlags" TEXT,
    "statusUpdatedAt" TIMESTAMP(3),

    CONSTRAINT "Stock_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StockInfoProfile" (
    "symbol" TEXT NOT NULL,
    "source" TEXT,
    "companyBasicJson" TEXT,
    "summaryFinancialsJson" TEXT,
    "pe" DOUBLE PRECISION,
    "pbr" DOUBLE PRECISION,
    "debtRatio" DOUBLE PRECISION,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "StockInfoProfile_pkey" PRIMARY KEY ("symbol")
);

-- CreateTable
CREATE TABLE "Strategy" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "settings" TEXT NOT NULL,
    "strategyType" TEXT NOT NULL DEFAULT '기타',
    "isSaved" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "deletedAt" TIMESTAMP(3),

    CONSTRAINT "Strategy_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BacktestRun" (
    "id" TEXT NOT NULL,
    "strategyId" TEXT NOT NULL,
    "market" TEXT,
    "universe" TEXT,
    "timeframe" TEXT NOT NULL DEFAULT '1d',
    "startDate" TEXT,
    "endDate" TEXT,
    "initialCapital" DOUBLE PRECISION NOT NULL,
    "commissionBps" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "slippageBps" DOUBLE PRECISION NOT NULL DEFAULT 0,
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
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BacktestRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StrategyEmbedding" (
    "id" TEXT NOT NULL,
    "strategyId" TEXT NOT NULL,
    "embeddingType" TEXT NOT NULL,
    "sourceText" TEXT NOT NULL,
    "vector" BYTEA,
    "sparseTokens" TEXT,
    "modelName" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyEmbedding_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AdviceExperience" (
    "id" TEXT NOT NULL,
    "strategyId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "market" TEXT,
    "universe" TEXT,
    "initialCapital" DOUBLE PRECISION NOT NULL,
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

    CONSTRAINT "AdviceExperience_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BatchRun" (
    "id" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "totalPrompts" INTEGER NOT NULL,
    "completedCount" INTEGER NOT NULL DEFAULT 0,
    "failedCount" INTEGER NOT NULL DEFAULT 0,
    "skippedCount" INTEGER NOT NULL DEFAULT 0,
    "rankingSnapshot" TEXT NOT NULL,
    "logs" TEXT,

    CONSTRAINT "BatchRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BatchRunCandidate" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "strategyId" TEXT,
    "prompt" TEXT NOT NULL,
    "strategyName" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "errorMessage" TEXT,
    "metrics" TEXT,
    "rank" INTEGER,
    "backtestRequest" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BatchRunCandidate_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StrategyPromptExperiment" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "seed" INTEGER NOT NULL,
    "totalPrompts" INTEGER NOT NULL,
    "status" TEXT NOT NULL,
    "config" TEXT NOT NULL,
    "summary" TEXT,
    "resultFilePath" TEXT,
    "summaryFilePath" TEXT,
    "datasetFilePath" TEXT,
    "rulesFilePath" TEXT,
    "patternsFilePath" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "StrategyPromptExperiment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StrategyPromptExperimentCandidate" (
    "id" TEXT NOT NULL,
    "experimentId" TEXT NOT NULL,
    "promptId" TEXT NOT NULL,
    "prompt" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "complexity" TEXT NOT NULL,
    "riskProfile" TEXT NOT NULL,
    "expectedBlocks" TEXT NOT NULL,
    "parsedStrategy" TEXT,
    "strategyDsl" TEXT,
    "strategyId" TEXT,
    "status" TEXT NOT NULL,
    "errorType" TEXT,
    "errorMessage" TEXT,
    "metrics" TEXT,
    "qualityScore" DOUBLE PRECISION,
    "extractedBlocks" TEXT,
    "extractedParameters" TEXT,
    "coachLearningTags" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "StrategyPromptExperimentCandidate_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StrategyAdvisorLearningInsight" (
    "id" TEXT NOT NULL,
    "experimentId" TEXT NOT NULL,
    "insightType" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "payload" TEXT NOT NULL,
    "confidence" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyAdvisorLearningInsight_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "User" (
    "id" SERIAL NOT NULL,
    "email" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "password" TEXT NOT NULL,
    "planTier" TEXT NOT NULL DEFAULT 'FREE',
    "role" TEXT NOT NULL DEFAULT 'USER',
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "lastLoginAt" TIMESTAMP(3),
    "backtestUsageMonth" TEXT,
    "backtestCountThisMonth" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AdminAuditLog" (
    "id" TEXT NOT NULL,
    "adminId" INTEGER NOT NULL,
    "adminEmail" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "targetType" TEXT,
    "targetId" TEXT,
    "targetUserId" INTEGER,
    "beforeJson" TEXT,
    "afterJson" TEXT,
    "ip" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AdminAuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PlanConfig" (
    "planId" TEXT NOT NULL,
    "monthlyBacktestLimit" INTEGER,
    "maxStrategies" INTEGER,
    "maxVirtualAccounts" INTEGER,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PlanConfig_pkey" PRIMARY KEY ("planId")
);

-- CreateTable
CREATE TABLE "UserAsset" (
    "userId" INTEGER NOT NULL,
    "availableCash" DECIMAL(65,30) NOT NULL DEFAULT 10000000,
    "initialGrantAmount" DECIMAL(65,30) NOT NULL DEFAULT 10000000,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "UserAsset_pkey" PRIMARY KEY ("userId")
);

-- CreateTable
CREATE TABLE "ResearchRun" (
    "id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "goal" TEXT,
    "config" TEXT NOT NULL,
    "holdoutStart" TEXT NOT NULL,
    "seed" INTEGER NOT NULL,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "errorMessage" TEXT,
    "totalCandidates" INTEGER NOT NULL DEFAULT 0,
    "promotedCount" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "ResearchRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResearchCandidate" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "dslHash" TEXT NOT NULL,
    "dslJson" TEXT NOT NULL,
    "template" TEXT NOT NULL,
    "stage" TEXT NOT NULL DEFAULT 'GENERATED',
    "rejectionReason" TEXT,
    "prescreenMetrics" TEXT,
    "wfaResult" TEXT,
    "mcResult" TEXT,
    "optunaBest" TEXT,
    "holdoutMetrics" TEXT,
    "compositeScore" DOUBLE PRECISION,
    "robustnessScore" DOUBLE PRECISION,
    "deflatedSharpe" DOUBLE PRECISION,
    "promotedAccountId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ResearchCandidate_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResearchEvent" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "candidateId" TEXT,
    "level" TEXT NOT NULL DEFAULT 'INFO',
    "event" TEXT NOT NULL,
    "payload" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ResearchEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VirtualAccount" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "initialCash" DECIMAL(65,30) NOT NULL,
    "currentCash" DECIMAL(65,30) NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "strategyId" TEXT,
    "strategyName" TEXT,
    "tradingMode" TEXT NOT NULL DEFAULT 'manual',
    "delistingPolicy" TEXT NOT NULL DEFAULT 'AUTO_LIQUIDATE',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "closedAt" TIMESTAMP(3),

    CONSTRAINT "VirtualAccount_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AssetLedger" (
    "id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "accountId" TEXT,
    "type" TEXT NOT NULL,
    "amount" DECIMAL(65,30) NOT NULL,
    "balanceAfter" DECIMAL(65,30) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AssetLedger_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VirtualMarketLog" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "stockName" TEXT,
    "signalType" TEXT NOT NULL,
    "reason" TEXT,
    "price" DOUBLE PRECISION NOT NULL,
    "action" TEXT NOT NULL,
    "orderId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "VirtualMarketLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VirtualMarketState" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "startDate" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'stopped',
    "symbols" TEXT NOT NULL,
    "lastRefreshed" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "VirtualMarketState_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VirtualOrder" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT,
    "side" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "price" DECIMAL(65,30) NOT NULL,
    "filledPrice" DECIMAL(65,30),
    "status" TEXT NOT NULL,
    "filledAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "avgBuyPrice" DECIMAL(65,30),
    "fee" DECIMAL(65,30),
    "realizedPnl" DECIMAL(65,30),
    "tax" DECIMAL(65,30),

    CONSTRAINT "VirtualOrder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VirtualPosition" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "avgPrice" DECIMAL(65,30) NOT NULL,
    "currentPrice" DECIMAL(65,30),
    "openedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "peakPrice" DECIMAL(65,30),

    CONSTRAINT "VirtualPosition_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SearchCount" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "count" INTEGER NOT NULL DEFAULT 0,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "SearchCount_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WatchlistGroup" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "name" TEXT NOT NULL,
    "color" TEXT NOT NULL DEFAULT '#3B82F6',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "WatchlistGroup_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WatchlistSymbol" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "addedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "groupId" TEXT,

    CONSTRAINT "WatchlistSymbol_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsFetchCache" (
    "symbol" TEXT NOT NULL,
    "fetchedAt" TIMESTAMP(3) NOT NULL,
    "articleCount" INTEGER NOT NULL DEFAULT 0,
    "isFetching" BOOLEAN NOT NULL DEFAULT false,
    "fetchingUntil" TIMESTAMP(3),
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsFetchCache_pkey" PRIMARY KEY ("symbol")
);

-- CreateTable
CREATE TABLE "NewsArticle" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "summary" TEXT,
    "url" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "author" TEXT,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "crawledAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "category" TEXT,
    "language" TEXT NOT NULL DEFAULT 'ko',
    "bodyHash" TEXT,
    "canonicalId" TEXT,
    "isCanonical" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsArticle_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsArticleRaw" (
    "id" TEXT NOT NULL,
    "articleId" TEXT,
    "provider" TEXT NOT NULL,
    "externalId" TEXT,
    "title" TEXT NOT NULL,
    "body" TEXT,
    "url" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "author" TEXT,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "category" TEXT,
    "rawJson" TEXT NOT NULL,
    "crawledAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsArticleRaw_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsArticleSymbol" (
    "id" TEXT NOT NULL,
    "articleId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "companyName" TEXT,
    "scope" TEXT NOT NULL DEFAULT 'stock',
    "sector" TEXT,
    "relevance" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsArticleSymbol_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsEvent" (
    "id" TEXT NOT NULL,
    "articleId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "sentiment" TEXT NOT NULL,
    "severity" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "surprise" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "credibility" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "novelty" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "relevance" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "summary" TEXT,
    "riskFlags" TEXT,
    "affectedEntities" TEXT,
    "expectedHorizon" TEXT,
    "modelVersion" TEXT NOT NULL DEFAULT 'v1',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsImpact" (
    "id" TEXT NOT NULL,
    "articleId" TEXT NOT NULL,
    "symbol" TEXT,
    "impactDirection" TEXT NOT NULL,
    "impactScore" DOUBLE PRECISION NOT NULL,
    "confidenceScore" DOUBLE PRECISION NOT NULL,
    "expectedHorizon" TEXT NOT NULL,
    "expectedAlpha1d" DOUBLE PRECISION,
    "expectedAlpha5d" DOUBLE PRECISION,
    "volatilityJumpRisk" DOUBLE PRECISION,
    "riskAlertLevel" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL DEFAULT 'v1',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsImpact_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsSignal" (
    "id" TEXT NOT NULL,
    "articleId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "signalType" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "direction" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "validFrom" TIMESTAMP(3) NOT NULL,
    "validUntil" TIMESTAMP(3),
    "metadata" TEXT,
    "modelVersion" TEXT NOT NULL DEFAULT 'v1',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsIngestionLog" (
    "id" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "startedAt" TIMESTAMP(3) NOT NULL,
    "finishedAt" TIMESTAMP(3),
    "status" TEXT NOT NULL,
    "fetched" INTEGER NOT NULL DEFAULT 0,
    "deduplicated" INTEGER NOT NULL DEFAULT 0,
    "inserted" INTEGER NOT NULL DEFAULT 0,
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsIngestionLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsV2Article" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "normalizedTitle" TEXT NOT NULL,
    "summary" TEXT,
    "source" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "sentiment" TEXT,
    "sentimentScore" DOUBLE PRECISION,
    "impactLevel" TEXT,
    "marketEffect" TEXT,
    "relatedSymbols" TEXT,
    "aiSummary" TEXT,
    "embedding" BYTEA,
    "hash" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'analyzed',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsV2Article_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_raw" (
    "newsId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "normalizedTitle" TEXT NOT NULL,
    "titleHash" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "rawContent" TEXT,
    "contentQuality" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "news_raw_pkey" PRIMARY KEY ("newsId")
);

-- CreateTable
CREATE TABLE "news_analysis" (
    "newsId" TEXT NOT NULL,
    "sentiment" TEXT,
    "impactScore" DOUBLE PRECISION,
    "importance" TEXT,
    "summary" TEXT,
    "marketEffect" TEXT,
    "relatedSymbols" TEXT,
    "status" TEXT NOT NULL DEFAULT 'analyzed',
    "error" TEXT,
    "analyzedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "news_analysis_pkey" PRIMARY KEY ("newsId")
);

-- CreateTable
CREATE TABLE "news_symbol_map" (
    "id" SERIAL NOT NULL,
    "newsId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "companyName" TEXT,
    "relevance" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "evidence" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "news_symbol_map_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "stock_news_cache" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "newsId" TEXT NOT NULL,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "rankScore" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "cachedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "stock_news_cache_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsV2PriorityScore" (
    "symbol" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "tier" INTEGER NOT NULL DEFAULT 3,
    "queue" TEXT NOT NULL DEFAULT 'cold',
    "reason" TEXT,
    "isTrending" BOOLEAN NOT NULL DEFAULT false,
    "lastCollected" TIMESTAMP(3),
    "lastViewed" TIMESTAMP(3),
    "currentViewUntil" TIMESTAMP(3),
    "viewCount24h" INTEGER NOT NULL DEFAULT 0,
    "watchlistCount" INTEGER NOT NULL DEFAULT 0,
    "holdingCount" INTEGER NOT NULL DEFAULT 0,
    "searchCount24h" INTEGER NOT NULL DEFAULT 0,
    "volatility" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "turnover" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "marketCap" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "tradingValue" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "newsCount1h" INTEGER NOT NULL DEFAULT 0,
    "newsCount24h" INTEGER NOT NULL DEFAULT 0,
    "newsVelocity" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "indexMember" INTEGER NOT NULL DEFAULT 0,
    "aiImportance" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsV2PriorityScore_pkey" PRIMARY KEY ("symbol")
);

-- CreateTable
CREATE TABLE "NewsV2PriorityEvent" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "userId" TEXT,
    "weight" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "metadataJson" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsV2PriorityEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NewsV2CollectionQueueItem" (
    "symbol" TEXT NOT NULL,
    "queue" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "reason" TEXT,
    "isTrending" BOOLEAN NOT NULL DEFAULT false,
    "enqueuedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsV2CollectionQueueItem_pkey" PRIMARY KEY ("symbol")
);

-- CreateTable
CREATE TABLE "NewsV2CollectionStatus" (
    "symbol" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'NOT_COLLECTED',
    "lastSuccessAt" TIMESTAMP(3),
    "lastAttemptAt" TIMESTAMP(3),
    "lastError" TEXT,
    "attemptCount" INTEGER NOT NULL DEFAULT 0,
    "inFlightJobId" TEXT,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NewsV2CollectionStatus_pkey" PRIMARY KEY ("symbol")
);

-- CreateTable
CREATE TABLE "NewsV2IngestionLog" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "jobId" TEXT,
    "startedAt" TIMESTAMP(3) NOT NULL,
    "finishedAt" TIMESTAMP(3),
    "fetched" INTEGER NOT NULL DEFAULT 0,
    "deduped" INTEGER NOT NULL DEFAULT 0,
    "inserted" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL,
    "error" TEXT,

    CONSTRAINT "NewsV2IngestionLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DelistingAuditLog" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "actionType" TEXT NOT NULL,
    "previousStatus" TEXT,
    "newStatus" TEXT,
    "quantity" INTEGER,
    "executionPrice" DOUBLE PRECISION,
    "reason" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DelistingAuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "BacktestHistory_cacheKey_key" ON "BacktestHistory"("cacheKey");

-- CreateIndex
CREATE INDEX "BacktestHistory_strategyId_createdAt_idx" ON "BacktestHistory"("strategyId", "createdAt");

-- CreateIndex
CREATE INDEX "UserBacktestHistory_userId_savedAt_idx" ON "UserBacktestHistory"("userId", "savedAt");

-- CreateIndex
CREATE UNIQUE INDEX "UserBacktestHistory_userId_backtestHistoryId_key" ON "UserBacktestHistory"("userId", "backtestHistoryId");

-- CreateIndex
CREATE INDEX "BacktestResult_strategyId_createdAt_idx" ON "BacktestResult"("strategyId", "createdAt");

-- CreateIndex
CREATE INDEX "SavedValidation_userId_createdAt_idx" ON "SavedValidation"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "SavedValidation_userId_cacheKey_idx" ON "SavedValidation"("userId", "cacheKey");

-- CreateIndex
CREATE UNIQUE INDEX "Stock_symbol_key" ON "Stock"("symbol");

-- CreateIndex
CREATE INDEX "Stock_listingStatus_idx" ON "Stock"("listingStatus");

-- CreateIndex
CREATE INDEX "Strategy_userId_createdAt_idx" ON "Strategy"("userId", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "BacktestRun_cacheKey_key" ON "BacktestRun"("cacheKey");

-- CreateIndex
CREATE INDEX "BacktestRun_strategyId_idx" ON "BacktestRun"("strategyId");

-- CreateIndex
CREATE INDEX "BacktestRun_strategyId_createdAt_idx" ON "BacktestRun"("strategyId", "createdAt");

-- CreateIndex
CREATE INDEX "StrategyEmbedding_strategyId_idx" ON "StrategyEmbedding"("strategyId");

-- CreateIndex
CREATE INDEX "StrategyEmbedding_embeddingType_idx" ON "StrategyEmbedding"("embeddingType");

-- CreateIndex
CREATE INDEX "AdviceExperience_strategyId_idx" ON "AdviceExperience"("strategyId");

-- CreateIndex
CREATE INDEX "AdviceExperience_market_universe_idx" ON "AdviceExperience"("market", "universe");

-- CreateIndex
CREATE INDEX "AdviceExperience_confidence_idx" ON "AdviceExperience"("confidence");

-- CreateIndex
CREATE INDEX "BatchRun_createdAt_idx" ON "BatchRun"("createdAt");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_runId_createdAt_idx" ON "BatchRunCandidate"("runId", "createdAt");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_runId_status_idx" ON "BatchRunCandidate"("runId", "status");

-- CreateIndex
CREATE INDEX "BatchRunCandidate_strategyId_idx" ON "BatchRunCandidate"("strategyId");

-- CreateIndex
CREATE INDEX "StrategyPromptExperiment_createdAt_idx" ON "StrategyPromptExperiment"("createdAt");

-- CreateIndex
CREATE INDEX "StrategyPromptExperiment_status_idx" ON "StrategyPromptExperiment"("status");

-- CreateIndex
CREATE INDEX "StrategyPromptExperimentCandidate_experimentId_createdAt_idx" ON "StrategyPromptExperimentCandidate"("experimentId", "createdAt");

-- CreateIndex
CREATE INDEX "StrategyPromptExperimentCandidate_experimentId_status_idx" ON "StrategyPromptExperimentCandidate"("experimentId", "status");

-- CreateIndex
CREATE INDEX "StrategyPromptExperimentCandidate_strategyId_idx" ON "StrategyPromptExperimentCandidate"("strategyId");

-- CreateIndex
CREATE INDEX "StrategyPromptExperimentCandidate_category_idx" ON "StrategyPromptExperimentCandidate"("category");

-- CreateIndex
CREATE UNIQUE INDEX "StrategyPromptExperimentCandidate_experimentId_promptId_key" ON "StrategyPromptExperimentCandidate"("experimentId", "promptId");

-- CreateIndex
CREATE INDEX "StrategyAdvisorLearningInsight_experimentId_insightType_idx" ON "StrategyAdvisorLearningInsight"("experimentId", "insightType");

-- CreateIndex
CREATE INDEX "StrategyAdvisorLearningInsight_key_idx" ON "StrategyAdvisorLearningInsight"("key");

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE INDEX "AdminAuditLog_createdAt_idx" ON "AdminAuditLog"("createdAt");

-- CreateIndex
CREATE INDEX "AdminAuditLog_targetUserId_createdAt_idx" ON "AdminAuditLog"("targetUserId", "createdAt");

-- CreateIndex
CREATE INDEX "AdminAuditLog_adminId_createdAt_idx" ON "AdminAuditLog"("adminId", "createdAt");

-- CreateIndex
CREATE INDEX "ResearchRun_userId_status_idx" ON "ResearchRun"("userId", "status");

-- CreateIndex
CREATE INDEX "ResearchCandidate_runId_stage_idx" ON "ResearchCandidate"("runId", "stage");

-- CreateIndex
CREATE INDEX "ResearchCandidate_runId_compositeScore_idx" ON "ResearchCandidate"("runId", "compositeScore");

-- CreateIndex
CREATE UNIQUE INDEX "ResearchCandidate_runId_dslHash_key" ON "ResearchCandidate"("runId", "dslHash");

-- CreateIndex
CREATE INDEX "ResearchEvent_runId_createdAt_idx" ON "ResearchEvent"("runId", "createdAt");

-- CreateIndex
CREATE INDEX "VirtualAccount_userId_createdAt_idx" ON "VirtualAccount"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "VirtualAccount_userId_status_idx" ON "VirtualAccount"("userId", "status");

-- CreateIndex
CREATE INDEX "AssetLedger_userId_createdAt_idx" ON "AssetLedger"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "AssetLedger_accountId_createdAt_idx" ON "AssetLedger"("accountId", "createdAt");

-- CreateIndex
CREATE INDEX "AssetLedger_type_idx" ON "AssetLedger"("type");

-- CreateIndex
CREATE UNIQUE INDEX "VirtualMarketState_accountId_key" ON "VirtualMarketState"("accountId");

-- CreateIndex
CREATE UNIQUE INDEX "VirtualPosition_accountId_symbol_key" ON "VirtualPosition"("accountId", "symbol");

-- CreateIndex
CREATE UNIQUE INDEX "SearchCount_symbol_key" ON "SearchCount"("symbol");

-- CreateIndex
CREATE INDEX "WatchlistGroup_userId_createdAt_idx" ON "WatchlistGroup"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "WatchlistSymbol_userId_addedAt_idx" ON "WatchlistSymbol"("userId", "addedAt");

-- CreateIndex
CREATE UNIQUE INDEX "WatchlistSymbol_userId_symbol_key" ON "WatchlistSymbol"("userId", "symbol");

-- CreateIndex
CREATE UNIQUE INDEX "NewsArticle_url_key" ON "NewsArticle"("url");

-- CreateIndex
CREATE INDEX "NewsArticle_publishedAt_idx" ON "NewsArticle"("publishedAt");

-- CreateIndex
CREATE INDEX "NewsArticle_source_publishedAt_idx" ON "NewsArticle"("source", "publishedAt");

-- CreateIndex
CREATE INDEX "NewsArticle_canonicalId_idx" ON "NewsArticle"("canonicalId");

-- CreateIndex
CREATE INDEX "NewsArticleRaw_provider_crawledAt_idx" ON "NewsArticleRaw"("provider", "crawledAt");

-- CreateIndex
CREATE INDEX "NewsArticleRaw_articleId_idx" ON "NewsArticleRaw"("articleId");

-- CreateIndex
CREATE INDEX "NewsArticleRaw_url_idx" ON "NewsArticleRaw"("url");

-- CreateIndex
CREATE INDEX "NewsArticleSymbol_articleId_idx" ON "NewsArticleSymbol"("articleId");

-- CreateIndex
CREATE INDEX "NewsArticleSymbol_symbol_idx" ON "NewsArticleSymbol"("symbol");

-- CreateIndex
CREATE INDEX "NewsArticleSymbol_symbol_createdAt_idx" ON "NewsArticleSymbol"("symbol", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "NewsEvent_articleId_key" ON "NewsEvent"("articleId");

-- CreateIndex
CREATE INDEX "NewsEvent_eventType_idx" ON "NewsEvent"("eventType");

-- CreateIndex
CREATE INDEX "NewsEvent_createdAt_idx" ON "NewsEvent"("createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "NewsImpact_articleId_key" ON "NewsImpact"("articleId");

-- CreateIndex
CREATE INDEX "NewsImpact_symbol_createdAt_idx" ON "NewsImpact"("symbol", "createdAt");

-- CreateIndex
CREATE INDEX "NewsImpact_riskAlertLevel_idx" ON "NewsImpact"("riskAlertLevel");

-- CreateIndex
CREATE INDEX "NewsSignal_symbol_validFrom_idx" ON "NewsSignal"("symbol", "validFrom");

-- CreateIndex
CREATE INDEX "NewsSignal_symbol_signalType_idx" ON "NewsSignal"("symbol", "signalType");

-- CreateIndex
CREATE INDEX "NewsIngestionLog_provider_createdAt_idx" ON "NewsIngestionLog"("provider", "createdAt");

-- CreateIndex
CREATE INDEX "NewsV2Article_symbol_publishedAt_idx" ON "NewsV2Article"("symbol", "publishedAt");

-- CreateIndex
CREATE INDEX "NewsV2Article_hash_idx" ON "NewsV2Article"("hash");

-- CreateIndex
CREATE INDEX "NewsV2Article_publishedAt_idx" ON "NewsV2Article"("publishedAt");

-- CreateIndex
CREATE UNIQUE INDEX "NewsV2Article_symbol_hash_key" ON "NewsV2Article"("symbol", "hash");

-- CreateIndex
CREATE UNIQUE INDEX "news_raw_url_key" ON "news_raw"("url");

-- CreateIndex
CREATE INDEX "news_raw_publishedAt_idx" ON "news_raw"("publishedAt");

-- CreateIndex
CREATE INDEX "news_raw_titleHash_idx" ON "news_raw"("titleHash");

-- CreateIndex
CREATE INDEX "news_raw_source_publishedAt_idx" ON "news_raw"("source", "publishedAt");

-- CreateIndex
CREATE INDEX "news_analysis_analyzedAt_idx" ON "news_analysis"("analyzedAt");

-- CreateIndex
CREATE INDEX "news_symbol_map_symbol_idx" ON "news_symbol_map"("symbol");

-- CreateIndex
CREATE INDEX "news_symbol_map_newsId_idx" ON "news_symbol_map"("newsId");

-- CreateIndex
CREATE UNIQUE INDEX "news_symbol_map_newsId_symbol_key" ON "news_symbol_map"("newsId", "symbol");

-- CreateIndex
CREATE INDEX "stock_news_cache_symbol_publishedAt_idx" ON "stock_news_cache"("symbol", "publishedAt");

-- CreateIndex
CREATE INDEX "stock_news_cache_symbol_rankScore_idx" ON "stock_news_cache"("symbol", "rankScore");

-- CreateIndex
CREATE UNIQUE INDEX "stock_news_cache_symbol_newsId_key" ON "stock_news_cache"("symbol", "newsId");

-- CreateIndex
CREATE INDEX "NewsV2PriorityScore_tier_score_idx" ON "NewsV2PriorityScore"("tier", "score");

-- CreateIndex
CREATE INDEX "NewsV2PriorityScore_queue_score_idx" ON "NewsV2PriorityScore"("queue", "score");

-- CreateIndex
CREATE INDEX "NewsV2PriorityScore_isTrending_score_idx" ON "NewsV2PriorityScore"("isTrending", "score");

-- CreateIndex
CREATE INDEX "NewsV2PriorityEvent_symbol_createdAt_idx" ON "NewsV2PriorityEvent"("symbol", "createdAt");

-- CreateIndex
CREATE INDEX "NewsV2PriorityEvent_eventType_createdAt_idx" ON "NewsV2PriorityEvent"("eventType", "createdAt");

-- CreateIndex
CREATE INDEX "NewsV2CollectionQueueItem_queue_score_idx" ON "NewsV2CollectionQueueItem"("queue", "score");

-- CreateIndex
CREATE INDEX "NewsV2CollectionQueueItem_updatedAt_idx" ON "NewsV2CollectionQueueItem"("updatedAt");

-- CreateIndex
CREATE INDEX "NewsV2IngestionLog_symbol_startedAt_idx" ON "NewsV2IngestionLog"("symbol", "startedAt");

-- CreateIndex
CREATE INDEX "DelistingAuditLog_accountId_createdAt_idx" ON "DelistingAuditLog"("accountId", "createdAt");

-- CreateIndex
CREATE INDEX "DelistingAuditLog_symbol_createdAt_idx" ON "DelistingAuditLog"("symbol", "createdAt");

-- AddForeignKey
ALTER TABLE "BacktestHistory" ADD CONSTRAINT "BacktestHistory_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UserBacktestHistory" ADD CONSTRAINT "UserBacktestHistory_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UserBacktestHistory" ADD CONSTRAINT "UserBacktestHistory_backtestHistoryId_fkey" FOREIGN KEY ("backtestHistoryId") REFERENCES "BacktestHistory"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BacktestResult" ADD CONSTRAINT "BacktestResult_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BacktestResult" ADD CONSTRAINT "BacktestResult_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SavedValidation" ADD CONSTRAINT "SavedValidation_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StockInfoProfile" ADD CONSTRAINT "StockInfoProfile_symbol_fkey" FOREIGN KEY ("symbol") REFERENCES "Stock"("symbol") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Strategy" ADD CONSTRAINT "Strategy_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BacktestRun" ADD CONSTRAINT "BacktestRun_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StrategyEmbedding" ADD CONSTRAINT "StrategyEmbedding_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AdviceExperience" ADD CONSTRAINT "AdviceExperience_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BatchRunCandidate" ADD CONSTRAINT "BatchRunCandidate_runId_fkey" FOREIGN KEY ("runId") REFERENCES "BatchRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BatchRunCandidate" ADD CONSTRAINT "BatchRunCandidate_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StrategyPromptExperimentCandidate" ADD CONSTRAINT "StrategyPromptExperimentCandidate_experimentId_fkey" FOREIGN KEY ("experimentId") REFERENCES "StrategyPromptExperiment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StrategyAdvisorLearningInsight" ADD CONSTRAINT "StrategyAdvisorLearningInsight_experimentId_fkey" FOREIGN KEY ("experimentId") REFERENCES "StrategyPromptExperiment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UserAsset" ADD CONSTRAINT "UserAsset_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResearchRun" ADD CONSTRAINT "ResearchRun_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResearchCandidate" ADD CONSTRAINT "ResearchCandidate_runId_fkey" FOREIGN KEY ("runId") REFERENCES "ResearchRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResearchEvent" ADD CONSTRAINT "ResearchEvent_runId_fkey" FOREIGN KEY ("runId") REFERENCES "ResearchRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "VirtualAccount" ADD CONSTRAINT "VirtualAccount_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AssetLedger" ADD CONSTRAINT "AssetLedger_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AssetLedger" ADD CONSTRAINT "AssetLedger_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "VirtualMarketState" ADD CONSTRAINT "VirtualMarketState_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "VirtualOrder" ADD CONSTRAINT "VirtualOrder_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "VirtualPosition" ADD CONSTRAINT "VirtualPosition_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WatchlistGroup" ADD CONSTRAINT "WatchlistGroup_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WatchlistSymbol" ADD CONSTRAINT "WatchlistSymbol_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WatchlistSymbol" ADD CONSTRAINT "WatchlistSymbol_groupId_fkey" FOREIGN KEY ("groupId") REFERENCES "WatchlistGroup"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NewsArticleRaw" ADD CONSTRAINT "NewsArticleRaw_articleId_fkey" FOREIGN KEY ("articleId") REFERENCES "NewsArticle"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NewsArticleSymbol" ADD CONSTRAINT "NewsArticleSymbol_articleId_fkey" FOREIGN KEY ("articleId") REFERENCES "NewsArticle"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NewsEvent" ADD CONSTRAINT "NewsEvent_articleId_fkey" FOREIGN KEY ("articleId") REFERENCES "NewsArticle"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NewsImpact" ADD CONSTRAINT "NewsImpact_articleId_fkey" FOREIGN KEY ("articleId") REFERENCES "NewsArticle"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NewsSignal" ADD CONSTRAINT "NewsSignal_articleId_fkey" FOREIGN KEY ("articleId") REFERENCES "NewsArticle"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DelistingAuditLog" ADD CONSTRAINT "DelistingAuditLog_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;

