-- 대화 기록에 그 턴의 전략 카드(2026-09-30) — 답변 텍스트에는 카드가 "[전략 요약 카드]"
-- 자리표시자로만 남아, 사용자가 입력한 전략을 우리가 어떻게 해석했는지 콘솔에서 볼 수 없었다.
-- {summaryItems: 화면 카드 항목, parsed: 해석 원본} JSON. additive: 기존 행은 NULL, 기존 코드 무영향.
ALTER TABLE "ChatQaLog" ADD COLUMN "strategySnapshot" TEXT;
