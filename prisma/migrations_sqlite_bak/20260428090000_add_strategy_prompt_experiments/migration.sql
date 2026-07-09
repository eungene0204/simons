CREATE TABLE "StrategyPromptExperiment" (
    "id" TEXT NOT NULL PRIMARY KEY,
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
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

CREATE TABLE "StrategyPromptExperimentCandidate" (
    "id" TEXT NOT NULL PRIMARY KEY,
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
    "qualityScore" REAL,
    "extractedBlocks" TEXT,
    "extractedParameters" TEXT,
    "coachLearningTags" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "StrategyPromptExperimentCandidate_experimentId_fkey" FOREIGN KEY ("experimentId") REFERENCES "StrategyPromptExperiment" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE "StrategyAdvisorLearningInsight" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "experimentId" TEXT NOT NULL,
    "insightType" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "payload" TEXT NOT NULL,
    "confidence" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "StrategyAdvisorLearningInsight_experimentId_fkey" FOREIGN KEY ("experimentId") REFERENCES "StrategyPromptExperiment" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "StrategyPromptExperiment_createdAt_idx" ON "StrategyPromptExperiment"("createdAt");
CREATE INDEX "StrategyPromptExperiment_status_idx" ON "StrategyPromptExperiment"("status");
CREATE UNIQUE INDEX "StrategyPromptExperimentCandidate_experimentId_promptId_key" ON "StrategyPromptExperimentCandidate"("experimentId", "promptId");
CREATE INDEX "StrategyPromptExperimentCandidate_experimentId_createdAt_idx" ON "StrategyPromptExperimentCandidate"("experimentId", "createdAt");
CREATE INDEX "StrategyPromptExperimentCandidate_experimentId_status_idx" ON "StrategyPromptExperimentCandidate"("experimentId", "status");
CREATE INDEX "StrategyPromptExperimentCandidate_strategyId_idx" ON "StrategyPromptExperimentCandidate"("strategyId");
CREATE INDEX "StrategyPromptExperimentCandidate_category_idx" ON "StrategyPromptExperimentCandidate"("category");
CREATE INDEX "StrategyAdvisorLearningInsight_experimentId_insightType_idx" ON "StrategyAdvisorLearningInsight"("experimentId", "insightType");
CREATE INDEX "StrategyAdvisorLearningInsight_key_idx" ON "StrategyAdvisorLearningInsight"("key");
