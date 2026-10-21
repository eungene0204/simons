-- 연구노트 DB 저장(2026-10-21) — additive: 새 테이블뿐이라 기존 코드 무영향.
CREATE TABLE "ResearchNote" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "published" VARCHAR(10) NOT NULL,
    "updated" VARCHAR(10) NOT NULL,
    "sections" JSONB NOT NULL,
    "related" JSONB NOT NULL,
    "faq" JSONB,
    "status" TEXT NOT NULL DEFAULT 'PUBLISHED',
    "sortKey" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ResearchNote_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ResearchNote_slug_key" ON "ResearchNote"("slug");
CREATE INDEX "ResearchNote_status_published_idx" ON "ResearchNote"("status", "published");
