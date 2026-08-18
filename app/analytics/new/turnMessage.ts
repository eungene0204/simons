/** 턴 응답 조립기 — assistant 메시지를 만드는 **유일한** 자리.
 *
 * 분기마다 손으로 메시지를 조립하던 구조에서 나온 사고들이 이 파일의 존재 이유다:
 *  · 인사 한 마디에 열려 있던 되묻기가 통째로 사라짐(FR-SA-015)
 *  · 안내 문구만 나가고 진행률 카드·선택지가 빠짐(FR-SA-016)
 *  · 질문은 '익절'인데 선택지는 '리밸런싱' — 질문과 칩을 다른 출처에서 가져옴
 * 규칙을 한 곳에 모으면 이런 조합은 만들 수 없다.
 *
 * 칩 채널이 둘인 것은 의미가 다르기 때문이다(합치면 안 된다):
 *  · `clarificationSuggestions` — 되묻기 선택지. 클릭이 결정론 귀속 경로를 탄다
 *    (handleSuggestionClick → applyDeterministicConditionChoice, 백엔드 왕복 없음).
 *  · `infoSuggestions` — 안내·빌더 프롬프트 칩. 클릭이 새 발화로 다시 전송된다.
 */
import type { BuilderProgressItem, BuilderSummaryItem } from "./builderProgressPresentation";
import type { ConversationDecision } from "./conversationDecision";

export type TurnPresentation = {
  summaryItems: BuilderSummaryItem[];
  progressItems: BuilderProgressItem[];
};

/** 아직 답하지 않은 되묻기 스냅샷(질문·선택지·그때의 카드). */
export type OpenClarification<TParsed = unknown> = {
  parsed?: TParsed;
  clarification?: string;
  clarificationSuggestions?: string[];
  clarificationField?: string;
  builderPresentation?: TurnPresentation;
  strategyConfirmation?: boolean;
  previousStepState?: unknown;
};

export type TurnMessage<TParsed = unknown> = {
  isLoading?: boolean;
  /** 유지/변경을 고르는 체크박스 목록(FR-SA-020). 목록 자체는 화면이 상태에서 만든다. */
  keepItems?: unknown[];
  infoText?: string;
  infoSuggestions?: string[];
  parsed?: TParsed;
  clarification?: string;
  clarificationSuggestions?: string[];
  /** 이 되묻기가 채우는 골격 슬롯(`MissingBacktestCondition["field"]`). 선택지가 닫힌
   *  집합인지 판정하는 입력이다 — 질문 문구는 사용자 친화 문구로 바뀌므로 근거가 못 된다. */
  clarificationField?: string;
  builderPresentation?: TurnPresentation;
  strategyConfirmation?: boolean;
  previousStepState?: unknown;
  coachLoading?: boolean;
  coachText?: string;
};

export type BuildTurnMessageInput<TParsed = unknown> = {
  decision: ConversationDecision;
  /** ask_keep_items 턴에서 보여줄 현재 설정 항목(상태에서 생성). */
  keepItems?: unknown[];
  /** 현재 전략의 요약·진행률 카드(전략이 없으면 undefined). */
  presentation?: TurnPresentation;
  /** 되묻기 질문에 맞춰 다시 만든 카드 — 없으면 `presentation`을 쓴다. */
  askPresentation?: TurnPresentation;
  /** 아직 답하지 않은 되묻기 — `preservesOpenQuestion` 턴에서만 되살린다. */
  openClarification?: OpenClarification<TParsed> | null;
  /** 되묻기 렌더에 필요한 현재 전략(clarification 블록은 parsed가 있어야 그려진다). */
  parsed?: TParsed | null;
  /** 네트워크로 받아온 답변 문구(지식 질문 등) — decision.message보다 우선한다. */
  answerText?: string;
};

/** 이 액션이 스스로 질문을 던지는가 — 그렇다면 열린 되묻기를 되살리면 질문이 겹친다. */
function asksItsOwnQuestion(decision: ConversationDecision): boolean {
  return (
    (decision.action === "respond" && Boolean(decision.opensClarification)) ||
    decision.action === "ask_keep_items" ||
    decision.action === "ask_next_condition" ||
    decision.action === "ask_holding_period" ||
    decision.action === "ask_research_metric"
  );
}

export function buildTurnMessage<TParsed = unknown>(
  input: BuildTurnMessageInput<TParsed>,
): TurnMessage<TParsed> {
  const {
    decision, presentation, askPresentation, openClarification, parsed, answerText, keepItems,
  } = input;

  // ⓪ 유지/변경 선택 — 안내문 아래 체크박스 목록을 세운다. 목록이 비면(설정된 항목이
  //    하나도 없음) 세울 것이 없으므로 일반 안내로 떨어진다.
  if (decision.action === "ask_keep_items" && keepItems && keepItems.length > 0) {
    return {
      isLoading: false,
      coachLoading: false,
      coachText: undefined,
      infoText: decision.message,
      infoSuggestions: undefined,
      parsed: parsed ?? undefined,
      keepItems,
      builderPresentation: presentation,
    };
  }

  // ① 상태가 정한 되묻기 — 질문·선택지·카드가 한 판정에서 나온다(FR-SA-016).
  if (decision.action === "ask_next_condition") {
    return {
      isLoading: false,
      coachLoading: false,
      coachText: undefined,
      infoText: undefined,
      infoSuggestions: undefined,
      parsed: parsed ?? undefined,
      clarification: decision.message,
      clarificationSuggestions: decision.suggestions,
      clarificationField: decision.field,
      builderPresentation: askPresentation ?? presentation,
    };
  }

  // ①' 되묻기 레인(L2')이 던지는 질문 — 값 없는 수정 대상("손절 바꿔줘")의 되묻기.
  //    상태 되묻기(①)와 같은 성격의 질문이므로 같은 카드(clarification 채널)로 나간다.
  //    예전에는 respond 액션이라 infoText+infoSuggestions로 나가 맨 텍스트+칩으로 보였다
  //    (2026-08-16 빌더 질문 카드 통일에서 남은 경로, 2026-08-17 사용자 신고). 칩 클릭은
  //    두 채널 모두 handleSuggestionClick을 타고, 진행 골격 슬롯의 결정론 칩이 아니면
  //    새 발화로 재전송된다 — 수정 칩("손절을 -5%로 변경")의 경로는 그대로다.
  if (decision.action === "respond" && decision.opensClarification) {
    return {
      isLoading: false,
      coachLoading: false,
      coachText: undefined,
      infoText: undefined,
      infoSuggestions: undefined,
      parsed: parsed ?? undefined,
      clarification: decision.message,
      clarificationSuggestions: decision.suggestions,
      builderPresentation: askPresentation ?? presentation,
    };
  }

  // ② 안내·답변 턴. 전략이 있으면 요약·진행률 카드를 **항상** 함께 보여준다
  //    (안내가 전략 맥락 없이 떠 있지 않도록 — 사용자 결정 2026-07-26).
  const message: TurnMessage<TParsed> = {
    isLoading: false,
    infoText: answerText ?? ("message" in decision ? decision.message ?? undefined : undefined),
    infoSuggestions:
      "suggestions" in decision && decision.suggestions?.length
        ? decision.suggestions
        : undefined,
    builderPresentation: presentation,
  };

  // ③ 전략 State를 건드리지 않는 부가 발화는 열려 있던 되묻기를 그대로 다시 세운다
  //    (FR-SA-015). 스스로 질문을 던지는 턴에는 붙이지 않는다 — 질문이 두 개가 된다.
  if (decision.preservesOpenQuestion && openClarification && !asksItsOwnQuestion(decision)) {
    return {
      ...message,
      ...openClarification,
      // 질문 당시의 카드를 우선한다 — 없으면 이 턴이 준비한 카드를 그대로 쓴다.
      builderPresentation: openClarification.builderPresentation ?? message.builderPresentation,
    };
  }
  return message;
}
