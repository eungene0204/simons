-- 전략 공개/비공개(2026-10-20) — 공개 전략은 '전략공유' 화면에 카드로 실린다.
-- additive: 기존 전략은 모두 비공개(false)로 시작, 기존 코드 무영향.
ALTER TABLE "Strategy" ADD COLUMN "isPublic" BOOLEAN NOT NULL DEFAULT false;
