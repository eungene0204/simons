-- 전략 대화의 서버 쪽 기억(2026-11-14) — additive: 새 테이블뿐이라 기존 코드 무영향.
CREATE TABLE "StrategyConversationTurn" (
    "id" TEXT NOT NULL,
    "draftId" TEXT NOT NULL,
    "turn" INTEGER NOT NULL,
    "utterance" TEXT NOT NULL,
    "question" TEXT,
    "stateHash" TEXT NOT NULL,
    "feasibility" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyConversationTurn_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "StrategyConversationTurn_draftId_turn_idx" ON "StrategyConversationTurn"("draftId", "turn");
CREATE INDEX "StrategyConversationTurn_createdAt_idx" ON "StrategyConversationTurn"("createdAt");
