-- 연간 결제(1년 선불·20% 할인) 도입(2026-09-13) — additive, 기존 데이터 무영향.
-- 기존 구독·주문은 모두 월간이므로 기본값 'monthly'로 채워진다.
ALTER TABLE "User" ADD COLUMN "billingCycle" TEXT NOT NULL DEFAULT 'monthly';
ALTER TABLE "PaymentOrder" ADD COLUMN "billingCycle" TEXT NOT NULL DEFAULT 'monthly';
