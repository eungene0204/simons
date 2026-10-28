-- 전략 시뮬레이션 예시 전환(2026-10-28) — 예시 전략 원본 결과 캐시. additive: 새 테이블 하나, 기존 테이블 무변경.
CREATE TABLE "ExampleSimulationResult" (
    "id" TEXT NOT NULL,
    "snapshotHash" TEXT NOT NULL,
    "dataAsOf" TEXT,
    "engineVersion" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "reason" TEXT,
    "result" TEXT,
    "computedAt" TIMESTAMP(3),
    "refreshLeaseUntil" TIMESTAMP(3),
    "lastAttemptAt" TIMESTAMP(3),
    "lastError" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ExampleSimulationResult_pkey" PRIMARY KEY ("id")
);
