-- AlterTable
ALTER TABLE "User" ADD COLUMN     "billingFailCount" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "nextBillingAt" TIMESTAMP(3),
ADD COLUMN     "subscriptionCanceledAt" TIMESTAMP(3),
ADD COLUMN     "subscriptionPlanId" TEXT,
ADD COLUMN     "tossBillingKey" TEXT;
