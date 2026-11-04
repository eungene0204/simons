-- 연구노트 원본 백테스트 결과(2026-11-04) — additive: 새 테이블뿐이라 기존 코드 무영향.
CREATE TABLE "ResearchNoteResult" (
    "slug" TEXT NOT NULL,
    "engineVersion" TEXT NOT NULL,
    "request" JSONB NOT NULL,
    "result" JSONB NOT NULL,
    "sensitivity" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ResearchNoteResult_pkey" PRIMARY KEY ("slug")
);
