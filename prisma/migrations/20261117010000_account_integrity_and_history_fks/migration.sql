-- 가상계좌 정합성·이력 보존 제약(2026-11-17).
-- 대상 테이블은 모두 수백 행 규모(운영 실측: VirtualOrder 575·VirtualMarketLog 574·Strategy 409)라
-- CONCURRENTLY 없이 한 트랜잭션으로 적용한다. 잠금 대기가 길어지면 배포를 멈추도록 lock_timeout을 건다.
SET lock_timeout = '5s';

-- ① 가상계좌는 같은 사용자의 전략만 가리킨다 — 남의 전략 id로 자동매매가 돌던 구멍을 DB에서 막는다.
--    어긋난 연결(남의 전략·없는 전략)은 먼저 끊는다(2026-11-17 운영 실측 0건).
UPDATE "VirtualAccount" a SET "strategyId" = NULL
WHERE a."userId" IS NOT NULL AND a."strategyId" IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM "Strategy" s WHERE s."id" = a."strategyId" AND s."userId" = a."userId");
CREATE UNIQUE INDEX "Strategy_userId_id_key" ON "Strategy"("userId", "id");
ALTER TABLE "VirtualAccount" ADD CONSTRAINT "VirtualAccount_userId_strategyId_fkey" FOREIGN KEY ("userId", "strategyId") REFERENCES "Strategy"("userId", "id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- ② 시장 로그는 계좌와 함께 사라진다 — 계좌 없는 로그는 먼저 지운다(운영 실측 0건).
DELETE FROM "VirtualMarketLog" l WHERE NOT EXISTS (SELECT 1 FROM "VirtualAccount" a WHERE a."id" = l."accountId");
ALTER TABLE "VirtualMarketLog" ADD CONSTRAINT "VirtualMarketLog_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "VirtualAccount"("id") ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "VirtualMarketLog_accountId_createdAt_idx" ON "VirtualMarketLog"("accountId", "createdAt");
CREATE INDEX "VirtualMarketLog_accountId_date_idx" ON "VirtualMarketLog"("accountId", "date");

-- ③ 주문 조회(자동매매 PENDING 조회·주문 목록·정산)용 인덱스 — FK accountId도 덮는다.
CREATE INDEX "VirtualOrder_accountId_status_createdAt_idx" ON "VirtualOrder"("accountId", "status", "createdAt");

-- ④ 결제·원장 이력은 사용자 하드 삭제로 지워지지 않는다(CASCADE → RESTRICT).
ALTER TABLE "PaymentOrder" DROP CONSTRAINT "PaymentOrder_userId_fkey",
  ADD CONSTRAINT "PaymentOrder_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "AssetLedger" DROP CONSTRAINT "AssetLedger_userId_fkey",
  ADD CONSTRAINT "AssetLedger_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- ⑤ 전략에서 파생된 학습 사본은 전략과 함께 지운다(RESTRICT 때문에 전략 삭제가 실패하던 문제).
ALTER TABLE "AdviceExperience" DROP CONSTRAINT "AdviceExperience_strategyId_fkey",
  ADD CONSTRAINT "AdviceExperience_strategyId_fkey" FOREIGN KEY ("strategyId") REFERENCES "Strategy"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- ⑥ 대화 턴 번호는 초안 안에서 하나뿐이다 — 겹친 행은 늦은 쪽을 지운다(운영 실측 0건, 3일 보관 데이터).
DELETE FROM "StrategyConversationTurn" WHERE "id" IN (
  SELECT "id" FROM (
    SELECT "id", row_number() OVER (PARTITION BY "draftId", "turn" ORDER BY "createdAt", "id") AS rn
    FROM "StrategyConversationTurn"
  ) d WHERE d.rn > 1
);
CREATE UNIQUE INDEX "StrategyConversationTurn_draftId_turn_key" ON "StrategyConversationTurn"("draftId", "turn");
DROP INDEX "StrategyConversationTurn_draftId_turn_idx";

RESET lock_timeout;
