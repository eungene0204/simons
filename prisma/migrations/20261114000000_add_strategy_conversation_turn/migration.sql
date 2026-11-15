-- 전략 대화의 서버 쪽 기억(2026-11-14) — additive: 새 테이블뿐이라 기존 코드 무영향.
CREATE TABLE "StrategyConversationTurn" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
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

-- 소유자 — 계정이 지워지면 그 계정의 대화 기록도 함께 지운다(비로그인 대화는 NULL).
ALTER TABLE "StrategyConversationTurn" ADD CONSTRAINT "StrategyConversationTurn_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
