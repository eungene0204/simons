-- 백테스트 기록에 원문 프롬프트를 스냅샷으로 저장한다.
-- 그동안 프롬프트는 BacktestHistory에 없어 상세 조회 시 원천 Strategy를 이름 매칭으로
-- 역추적해야 했다(동명 전략 충돌·전략 삭제 시 깨짐). 프롬프트를 conditions/metrics처럼
-- 기록 자체에 스냅샷으로 박아 SOT를 기록과 함께 보존한다.
ALTER TABLE "BacktestHistory" ADD COLUMN "prompt" TEXT;

-- 백필: strategyId 직결 기록은 해당 Strategy의 원문(settings.description 우선)으로 채운다.
UPDATE "BacktestHistory"
SET "prompt" = (
  SELECT COALESCE(NULLIF(TRIM(json_extract(s."settings", '$.description')), ''), s."description")
  FROM "Strategy" s
  WHERE s."id" = "BacktestHistory"."strategyId"
)
WHERE "strategyId" IS NOT NULL
  AND ("prompt" IS NULL OR TRIM("prompt") = '');

-- 백필: strategyId가 없는 기록은 동일 이름의 가장 최근 Strategy에서 채운다.
UPDATE "BacktestHistory"
SET "prompt" = (
  SELECT COALESCE(NULLIF(TRIM(json_extract(s."settings", '$.description')), ''), s."description")
  FROM "Strategy" s
  WHERE s."name" = "BacktestHistory"."strategyName"
  ORDER BY s."createdAt" DESC
  LIMIT 1
)
WHERE "strategyId" IS NULL
  AND ("prompt" IS NULL OR TRIM("prompt") = '');
