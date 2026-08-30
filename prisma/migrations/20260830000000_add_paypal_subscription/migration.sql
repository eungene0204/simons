-- PayPal 정기구독(글로벌 /us) 스키마 (2026-08-30)
-- additive only — 기존 토스 결제 데이터·경로에 영향 없음(기존 행은 기본값으로 toss/KRW로 해석된다)

-- AlterTable
ALTER TABLE "User" ADD COLUMN     "paymentProvider" TEXT NOT NULL DEFAULT 'toss',
ADD COLUMN     "paypalPayerId" TEXT,
ADD COLUMN     "paypalSubscriptionId" TEXT;

-- AlterTable
ALTER TABLE "PaymentOrder" ADD COLUMN     "currency" TEXT NOT NULL DEFAULT 'KRW',
ADD COLUMN     "provider" TEXT NOT NULL DEFAULT 'toss';

-- CreateTable
CREATE TABLE "PaymentWebhookEvent" (
    "id" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "eventId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "receivedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PaymentWebhookEvent_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_paypalSubscriptionId_key" ON "User"("paypalSubscriptionId");

-- CreateIndex
CREATE UNIQUE INDEX "PaymentWebhookEvent_provider_eventId_key" ON "PaymentWebhookEvent"("provider", "eventId");
