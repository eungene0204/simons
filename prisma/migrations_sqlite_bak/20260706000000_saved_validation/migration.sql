-- CreateTable
CREATE TABLE "SavedValidation" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER,
    "modelType" TEXT NOT NULL,
    "strategyName" TEXT NOT NULL,
    "prompt" TEXT,
    "cacheKey" TEXT,
    "settings" TEXT NOT NULL,
    "result" TEXT NOT NULL,
    "summary" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "SavedValidation_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "SavedValidation_userId_createdAt_idx" ON "SavedValidation"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "SavedValidation_userId_cacheKey_idx" ON "SavedValidation"("userId", "cacheKey");
