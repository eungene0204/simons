-- 업그레이드 전환 중 이전 PayPal 구독 보관(2026-08-31) — additive, 기존 데이터 무영향.
-- 새 구독이 활성화된 것을 확인한 뒤에야 이전 구독을 해지하기 위한 임시 보관소다
-- (먼저 해지하면 사용자가 승인을 이탈했을 때 구독을 잃는다).
ALTER TABLE "User" ADD COLUMN "paypalPriorSubscriptionId" TEXT;
