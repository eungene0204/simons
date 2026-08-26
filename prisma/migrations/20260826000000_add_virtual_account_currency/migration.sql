-- 가상계좌 통화 컬럼(2026-08-26) — /us 생성 계좌 USD, 기존 계좌는 KRW 기본값(additive, 데이터 무영향)
ALTER TABLE "VirtualAccount" ADD COLUMN "currency" TEXT NOT NULL DEFAULT 'KRW';
