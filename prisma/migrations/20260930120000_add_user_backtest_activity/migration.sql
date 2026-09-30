-- 사용자 백테스트 활동 지표(2026-09-30) — 한도 카운터(backtestCountThisMonth)는 결제 주기마다
-- 리셋되고 "내 목록"은 같은 전략을 한 행으로 합쳐, 관리자 콘솔이 사용자가 실제로 몇 번·언제
-- 실행했는지 알 길이 없었다. consumeBacktestQuota가 한도 소비와 함께 올린다.
-- additive: 기존 행은 0/NULL로 시작(과거 실행 횟수는 복원 불가), 기존 코드 무영향.
ALTER TABLE "User" ADD COLUMN "backtestRunTotal" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "User" ADD COLUMN "lastBacktestAt" TIMESTAMP(3);
