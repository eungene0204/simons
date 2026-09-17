-- 계정 이용 기한(2026-09-17) — 게스트 입장 링크를 정해진 시각에 막기 위해. 이 시각부터 로그인·기존 세션 모두 거부.
-- additive: nullable 컬럼만 추가, 기존 행은 null(무기한)이라 동작 무영향.
ALTER TABLE "User" ADD COLUMN "accessExpiresAt" TIMESTAMP(3);
