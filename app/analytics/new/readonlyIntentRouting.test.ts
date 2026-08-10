// 읽기 전용 라벨(STRATEGY_STATUS·RESULT_EXPLAIN) 라우팅 회귀 테스트.
//
// 이 라벨들이 없던 시절 "몇 단계까지 왔어?" 같은 발화는 UNKNOWN으로 떨어져 실패
// 안내를 받거나 전략 파싱으로 새어 무변경 요약만 다시 렌더링됐다(2026-08-11 커버리지
// 프로브). 고정할 계약은 셋이다:
//
// 1. 규제 게이트보다 **먼저** 라우팅된다(게이트 라벨이 아니다).
// 2. 결과가 없으면 결과 설명 레인으로 보내지 않는다 — 인용할 수치가 없다.
// 3. 열린 되묻기를 지우지 않는다(부가 발화이므로 진행 중인 질문이 살아남는다).

import { describe, expect, it } from "vitest";

import {
  decideConversationTurn,
  type ConversationContext,
  type SemanticClassification,
} from "./conversationDecision";

const baseContext: ConversationContext = {
  stage: "idle",
  hasBacktestRequest: false,
  hasCurrentStrategy: false,
  builderMode: false,
  lastCoachText: null,
};

const classify = (intent: SemanticClassification["intent"]): SemanticClassification => ({
  intent,
  workflowEffect: "NONE",
  workflowStatus: "ACTIVE",
});

describe("STRATEGY_STATUS 라우팅", () => {
  it("전략이 있으면 지금까지 정한 조건을 알리는 즉답으로 끝낸다", () => {
    const decision = decideConversationTurn(
      "내가 지금까지 뭘 정했지?",
      { ...baseContext, hasCurrentStrategy: true, stage: "ready" },
      classify("STRATEGY_STATUS"),
    );

    expect(decision).toMatchObject({
      action: "respond",
      reason: "classified_strategy_status",
      preservesOpenQuestion: true,
    });
    expect(decision.action === "respond" && decision.message).toContain("지금까지 정한 조건");
  });

  it("전략이 없으면 정해진 조건이 없다고 알린다", () => {
    const decision = decideConversationTurn(
      "내가 지금까지 뭘 정했지?",
      baseContext,
      classify("STRATEGY_STATUS"),
    );

    expect(decision).toMatchObject({ action: "respond", reason: "classified_strategy_status" });
    expect(decision.action === "respond" && decision.message).toContain("아직 정해진 조건이 없어요");
  });

  it("전략 파싱 레인으로 새지 않는다 — 묻기만 한 발화가 전략을 바꾸면 안 된다", () => {
    const decision = decideConversationTurn(
      "아까 손절 몇 퍼센트로 했었지?",
      { ...baseContext, hasCurrentStrategy: true },
      classify("STRATEGY_STATUS"),
    );

    expect(decision.action).toBe("respond");
  });
});

describe("종목 지표 값 조회 라우팅 (규제 게이트 분리)", () => {
  const factClassification: SemanticClassification = {
    intent: "STOCK_ANALYSIS",
    factMetric: "per",
    suggestedReply: "삼성전자의 PER(주가수익비율)은(는) **35.04배**입니다.",
    workflowEffect: "NONE",
  };

  it("값 조회 턴은 백엔드가 만든 사실 문장을 그대로 보여준다", () => {
    const decision = decideConversationTurn(
      "삼성전자 PER이 얼마야?",
      baseContext,
      factClassification,
    );

    expect(decision).toMatchObject({ action: "respond_stock", reason: "stock_fact_lookup" });
    expect(decision.action === "respond_stock" && decision.message).toContain("35.04배");
  });

  it("판단 요청(지표 없음)은 종전대로 거절 안내를 쓴다", () => {
    const decision = decideConversationTurn(
      "삼성전자 지금 사도 될까?",
      baseContext,
      { intent: "STOCK_ANALYSIS", workflowEffect: "NONE" },
    );

    expect(decision).toMatchObject({
      action: "respond_stock",
      reason: "classified_stock_analysis",
    });
    expect(decision.action === "respond_stock" && decision.message).toContain(
      "매수·매도 판단이나 종목 추천은 제공하지 않아요",
    );
  });

  it("전략 진행 중에도 값 조회는 답한다 — 파싱 레인이 삼키지 않는다", () => {
    const decision = decideConversationTurn(
      "삼성전자 PER이 얼마야?",
      { ...baseContext, hasCurrentStrategy: true, stage: "ready" },
      factClassification,
    );

    expect(decision).toMatchObject({ action: "respond_stock", reason: "stock_fact_lookup" });
  });

  it("전략 진행 중 종목 추가 요청(지표 없음)은 종전대로 파싱 레인으로 간다", () => {
    const decision = decideConversationTurn(
      "제주반도체도 추가해줘",
      { ...baseContext, hasCurrentStrategy: true, stage: "ready" },
      { intent: "STOCK_ANALYSIS", workflowEffect: "NONE" },
    );

    expect(decision.reason).toBe("preserve_active_strategy");
  });
});

describe("업종·테마 소속 목록 라우팅 (규제 게이트 직교 축)", () => {
  const listClassification: SemanticClassification = {
    intent: "STOCK_PICK",
    listScope: "반도체",
    suggestedReply: "'반도체' 업종에 속한 상장사는 현재 총 77곳입니다 (가나다순).",
    workflowEffect: "NONE",
  };

  it("소속 질문은 백엔드가 만든 정본 목록을 그대로 보여준다 — 빌더로 보내지 않는다", () => {
    const decision = decideConversationTurn(
      "반도체 업종에 어떤 회사들이 있어?",
      baseContext,
      listClassification,
    );

    expect(decision).toMatchObject({ action: "respond", reason: "stock_membership_list" });
    expect(decision.action === "respond" && decision.message).toContain("총 77곳");
  });

  it("열린 추천(범위 없음)은 종전대로 빌더 전환이다", () => {
    const decision = decideConversationTurn(
      "뭐 사야 돼?",
      baseContext,
      { intent: "STOCK_PICK", suggestedReply: "안내", workflowEffect: "NONE" },
    );

    expect(decision.action).toBe("start_builder");
  });

  it("UNKNOWN 라벨이어도 목록이 성립하면 답한다 — '코스피200에 몇 종목?'의 실제 라벨", () => {
    const decision = decideConversationTurn(
      "코스피200에 몇 종목 들어있어?",
      baseContext,
      {
        intent: "UNKNOWN",
        listScope: "코스피200",
        suggestedReply: "'코스피200' 지수에 속한 상장사는 현재 총 200곳입니다 (가나다순).",
        workflowEffect: "NONE",
      },
    );

    expect(decision).toMatchObject({ action: "respond", reason: "stock_membership_list" });
    expect(decision.action === "respond" && decision.message).toContain("총 200곳");
  });

  it("전략 진행 중에도 소속 질문은 답한다 — 파싱 레인이 삼키지 않는다", () => {
    const decision = decideConversationTurn(
      "반도체 업종에 어떤 회사들이 있어?",
      { ...baseContext, hasCurrentStrategy: true, stage: "ready" },
      listClassification,
    );

    expect(decision).toMatchObject({ action: "respond", reason: "stock_membership_list" });
    // 진행 중이던 되묻기를 지우지 않는다 — 부가 질문이다.
    expect(decision.action === "respond" && decision.preservesOpenQuestion).toBe(true);
  });
});

describe("RESULT_EXPLAIN 라우팅", () => {
  it("결과가 있으면 사실 주입 답변 레인으로 보낸다", () => {
    const decision = decideConversationTurn(
      "승률은 높은데 수익이 왜 마이너스야?",
      {
        ...baseContext,
        hasCurrentStrategy: true,
        hasBacktestResult: true,
        stage: "done",
      },
      classify("RESULT_EXPLAIN"),
    );

    expect(decision).toMatchObject({
      action: "answer_result",
      reason: "classified_result_explain",
    });
  });

  it("결과가 없으면 답변 레인으로 보내지 않는다 — 인용할 수치가 없다", () => {
    const decision = decideConversationTurn(
      "MDD가 -35%면 심한 거야?",
      { ...baseContext, hasCurrentStrategy: true },
      classify("RESULT_EXPLAIN"),
    );

    expect(decision).toMatchObject({
      action: "respond",
      reason: "result_explain_without_result",
    });
    expect(decision.action === "respond" && decision.message).toContain("아직 백테스트 결과가 없어요");
  });
});
