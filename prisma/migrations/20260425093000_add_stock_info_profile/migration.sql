CREATE TABLE "StockInfoProfile" (
    "symbol" TEXT NOT NULL PRIMARY KEY,
    "source" TEXT,
    "companyBasicJson" TEXT,
    "summaryFinancialsJson" TEXT,
    "pe" REAL,
    "pbr" REAL,
    "debtRatio" REAL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "StockInfoProfile_symbol_fkey" FOREIGN KEY ("symbol") REFERENCES "Stock" ("symbol") ON DELETE CASCADE ON UPDATE CASCADE
);
