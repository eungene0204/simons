-- 백테스트 캐시가 자동 생성한 Strategy 행과 사용자가 명시적으로 저장한 행을 구분하는 플래그
ALTER TABLE "Strategy" ADD COLUMN "isSaved" BOOLEAN NOT NULL DEFAULT false;

-- 기존 데이터 백필: 캐시 자동 생성 시그니처(이름 "전략 <8자해시>" + userId 없음 + 설명 없음 + 기타 타입)에
-- 해당하지 않는 행은 사용자가 저장한 것으로 간주하여 노출 유지
UPDATE "Strategy"
SET "isSaved" = true
WHERE NOT (
  "userId" IS NULL
  AND "description" IS NULL
  AND "strategyType" = '기타'
  AND "name" LIKE '전략 %'
  AND length("name") = 11
);
