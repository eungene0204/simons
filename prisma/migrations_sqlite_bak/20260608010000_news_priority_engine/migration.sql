-- News Collection Priority Engine

ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "queue" TEXT NOT NULL DEFAULT 'cold';
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "reason" TEXT;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "isTrending" BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "currentViewUntil" DATETIME;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "holdingCount" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "marketCap" REAL NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "tradingValue" REAL NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "newsCount1h" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "newsCount24h" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "newsVelocity" REAL NOT NULL DEFAULT 0;
ALTER TABLE "NewsV2PriorityScore" ADD COLUMN "indexMember" INTEGER NOT NULL DEFAULT 0;

CREATE TABLE "NewsV2PriorityEvent" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "userId" TEXT,
    "weight" REAL NOT NULL DEFAULT 1,
    "metadataJson" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE "NewsV2CollectionQueueItem" (
    "symbol" TEXT NOT NULL,
    "queue" TEXT NOT NULL,
    "score" REAL NOT NULL DEFAULT 0,
    "reason" TEXT,
    "isTrending" BOOLEAN NOT NULL DEFAULT false,
    "enqueuedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,

    CONSTRAINT "NewsV2CollectionQueueItem_pkey" PRIMARY KEY ("symbol")
);

CREATE INDEX "NewsV2PriorityScore_queue_score_idx" ON "NewsV2PriorityScore"("queue", "score");
CREATE INDEX "NewsV2PriorityScore_isTrending_score_idx" ON "NewsV2PriorityScore"("isTrending", "score");
CREATE INDEX "NewsV2PriorityEvent_symbol_createdAt_idx" ON "NewsV2PriorityEvent"("symbol", "createdAt");
CREATE INDEX "NewsV2PriorityEvent_eventType_createdAt_idx" ON "NewsV2PriorityEvent"("eventType", "createdAt");
CREATE INDEX "NewsV2CollectionQueueItem_queue_score_idx" ON "NewsV2CollectionQueueItem"("queue", "score");
CREATE INDEX "NewsV2CollectionQueueItem_updatedAt_idx" ON "NewsV2CollectionQueueItem"("updatedAt");
