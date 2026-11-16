-- 코드 참조가 없고 운영에서 비어 있는 테이블을 지운다(2026-11-17 운영 실측: 셋 다 0행).
--   BacktestRun·StrategyEmbedding — 전략을 RESTRICT로 붙잡아 전략 삭제를 막던 미사용 테이블
--   StrategyVersion — 버전 이력 기능 삭제(0b49af16) 뒤 남은 테이블
-- 데이터는 되돌릴 수 없지만 지울 데이터가 없다. 각 테이블의 FK는 DROP TABLE이 함께 지운다.
SET lock_timeout = '5s';
DROP TABLE "BacktestRun";
DROP TABLE "StrategyEmbedding";
DROP TABLE "StrategyVersion";
RESET lock_timeout;
