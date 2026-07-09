-- News tab cache pipeline tables.
-- These tables separate raw collection, symbol mapping, analysis, and final tab cache.

PRAGMA busy_timeout=30000;

CREATE TABLE IF NOT EXISTS "news_raw" (
    "newsId" TEXT NOT NULL PRIMARY KEY,
    "title" TEXT NOT NULL,
    "normalizedTitle" TEXT NOT NULL,
    "titleHash" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "publishedAt" DATETIME NOT NULL,
    "rawContent" TEXT,
    "contentQuality" REAL NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "news_analysis" (
    "newsId" TEXT NOT NULL PRIMARY KEY,
    "sentiment" TEXT,
    "impactScore" REAL,
    "importance" TEXT,
    "summary" TEXT,
    "marketEffect" TEXT,
    "relatedSymbols" TEXT,
    "status" TEXT NOT NULL DEFAULT 'analyzed',
    "error" TEXT,
    "analyzedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "news_symbol_map" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "newsId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "companyName" TEXT,
    "relevance" REAL NOT NULL DEFAULT 1,
    "evidence" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "stock_news_cache" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "newsId" TEXT NOT NULL,
    "publishedAt" DATETIME NOT NULL,
    "rankScore" REAL NOT NULL DEFAULT 0,
    "cachedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS "news_raw_url_key" ON "news_raw"("url");
CREATE INDEX IF NOT EXISTS "idx_news_raw_published" ON "news_raw"("publishedAt");
CREATE INDEX IF NOT EXISTS "idx_news_raw_title_hash" ON "news_raw"("titleHash");
CREATE INDEX IF NOT EXISTS "idx_news_raw_source_published" ON "news_raw"("source", "publishedAt");

CREATE INDEX IF NOT EXISTS "idx_news_analysis_analyzed" ON "news_analysis"("analyzedAt");

CREATE UNIQUE INDEX IF NOT EXISTS "news_symbol_map_newsId_symbol_key" ON "news_symbol_map"("newsId", "symbol");
CREATE INDEX IF NOT EXISTS "idx_news_symbol_map_symbol" ON "news_symbol_map"("symbol");
CREATE INDEX IF NOT EXISTS "idx_news_symbol_map_news" ON "news_symbol_map"("newsId");

CREATE UNIQUE INDEX IF NOT EXISTS "stock_news_cache_symbol_newsId_key" ON "stock_news_cache"("symbol", "newsId");
CREATE INDEX IF NOT EXISTS "idx_stock_news_cache_symbol_published" ON "stock_news_cache"("symbol", "publishedAt");
CREATE INDEX IF NOT EXISTS "idx_stock_news_cache_symbol_rank" ON "stock_news_cache"("symbol", "rankScore");
