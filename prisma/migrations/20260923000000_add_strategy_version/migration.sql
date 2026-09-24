-- 내 전략 버전 이력(2026-09-23) — 전략을 저장할 때마다 그때의 설정을 한 줄씩 남긴다.
-- 전략 행의 id는 DSL 해시라 내용을 고치면 **다른 행**이 된다(같은 행이 갱신되지 않는다).
-- 그래서 이력은 사용자+전략 이름(lineageKey)으로 묶는다 — 사용자가 '같은 전략'이라고
-- 여기는 단위가 이름이기 때문이다. additive: 새 테이블만 추가, 기존 데이터 무영향.
CREATE TABLE "StrategyVersion" (
    "id" TEXT NOT NULL,
    "userId" INTEGER,
    "lineageKey" TEXT NOT NULL,
    "strategyId" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "settings" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyVersion_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "StrategyVersion_lineageKey_version_idx" ON "StrategyVersion"("lineageKey", "version");

CREATE INDEX "StrategyVersion_userId_createdAt_idx" ON "StrategyVersion"("userId", "createdAt");

ALTER TABLE "StrategyVersion" ADD CONSTRAINT "StrategyVersion_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
