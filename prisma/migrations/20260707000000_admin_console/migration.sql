-- AlterTable: User에 관리자 콘솔용 필드 추가
ALTER TABLE "User" ADD COLUMN "role" TEXT NOT NULL DEFAULT 'USER';
ALTER TABLE "User" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE "User" ADD COLUMN "lastLoginAt" DATETIME;

-- CreateTable: 관리자 작업 감사 로그
CREATE TABLE "AdminAuditLog" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "adminId" INTEGER NOT NULL,
    "adminEmail" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "targetType" TEXT,
    "targetId" TEXT,
    "targetUserId" INTEGER,
    "beforeJson" TEXT,
    "afterJson" TEXT,
    "ip" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE INDEX "AdminAuditLog_createdAt_idx" ON "AdminAuditLog"("createdAt");
CREATE INDEX "AdminAuditLog_targetUserId_createdAt_idx" ON "AdminAuditLog"("targetUserId", "createdAt");
CREATE INDEX "AdminAuditLog_adminId_createdAt_idx" ON "AdminAuditLog"("adminId", "createdAt");

-- CreateTable: 플랜별 한도 오버라이드
CREATE TABLE "PlanConfig" (
    "planId" TEXT NOT NULL PRIMARY KEY,
    "monthlyBacktestLimit" INTEGER,
    "maxStrategies" INTEGER,
    "maxVirtualAccounts" INTEGER,
    "updatedAt" DATETIME NOT NULL
);
