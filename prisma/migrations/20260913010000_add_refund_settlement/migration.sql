-- 중도 해지 정산(부분 환불) 기록(2026-09-13) — additive, 기존 데이터 무영향.
-- 기존 주문은 환불된 적이 없으므로 refundedAmount=0 / refundedAt=NULL로 채워진다.
ALTER TABLE "PaymentOrder" ADD COLUMN "refundedAmount" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "PaymentOrder" ADD COLUMN "refundedAt" TIMESTAMP(3);
