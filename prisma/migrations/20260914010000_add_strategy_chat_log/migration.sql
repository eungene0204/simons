-- 전략연구소 대화 기록(사용자용, 2026-09-14) — 브라우저 localStorage에 있던 왼쪽 대화 로그를 계정별 DB 저장으로 이관.
-- 계정당 최대 30건(LRU)은 애플리케이션이 지킨다. additive: 새 테이블만 추가, 기존 데이터 무영향.
CREATE TABLE "StrategyChatLog" (
    "id" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "sessionId" TEXT NOT NULL,
    "region" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "messageCount" INTEGER NOT NULL,
    "snapshot" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyChatLog_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "StrategyChatLog_userId_sessionId_key" ON "StrategyChatLog"("userId", "sessionId");

CREATE INDEX "StrategyChatLog_userId_updatedAt_idx" ON "StrategyChatLog"("userId", "updatedAt");

ALTER TABLE "StrategyChatLog" ADD CONSTRAINT "StrategyChatLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
