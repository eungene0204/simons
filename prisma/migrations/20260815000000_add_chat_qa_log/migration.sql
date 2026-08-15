-- CreateTable
CREATE TABLE "ChatQaLog" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "userEmail" TEXT,
    "sessionId" TEXT NOT NULL,
    "turnIndex" INTEGER NOT NULL,
    "question" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "answerKind" TEXT NOT NULL,
    "chipAnswer" BOOLEAN NOT NULL DEFAULT false,
    "latencyMs" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ChatQaLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ChatQaLog_createdAt_idx" ON "ChatQaLog"("createdAt");

-- CreateIndex
CREATE INDEX "ChatQaLog_userId_createdAt_idx" ON "ChatQaLog"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "ChatQaLog_sessionId_turnIndex_idx" ON "ChatQaLog"("sessionId", "turnIndex");
