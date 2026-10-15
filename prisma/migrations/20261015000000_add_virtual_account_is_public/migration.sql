-- 가상계좌 공개/비공개(2026-10-15) — 공개 계좌는 로그인 없이 링크로 읽기 전용 열람한다.
-- additive: 기존 계좌는 모두 비공개(false)로 시작, 기존 코드 무영향.
ALTER TABLE "VirtualAccount" ADD COLUMN "isPublic" BOOLEAN NOT NULL DEFAULT false;
