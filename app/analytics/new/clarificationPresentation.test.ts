import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  presentStrategyClarification,
  shouldContinueWithSingleAssetBuilder,
} from "./clarificationPresentation";

const complete: ParsedSummary = {
  description: "완성 전략",
  universe: ["KOSPI"],
  fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "monthly",
  // 리밸런싱을 켠 전략은 방식까지 정해져야 완성이다(FR-BT-067).
  rebalance_method: "reconstitute",
  stop_loss_pct: 10,
  take_profit_pct: 20,
  backtest_period: "5y",
  initial_capital: 10_000_000,
};

describe("presentStrategyClarification", () => {
  it("'익절 안 함'으로 거부한 익절은 다시 묻지 않는다(2026-11-12 기간 수정 뒤 반복 질문)", () => {
    expect(
      presentStrategyClarification({
        parsed: { ...complete, take_profit_pct: null },
        backendQuestion: null,
        gateOptions: { declinedFields: ["take_profit"] },
      }),
    ).toBeNull();
  });

  it("백엔드 질문보다 파싱 결과의 다음 누락 조건을 우선한다", () => {
    expect(
      presentStrategyClarification({
        parsed: { ...complete, take_profit_pct: null },
        backendQuestion: "익절 — 목표 수익 비율을 정해주세요",
        backendSuggestions: ["익절 20%"],
      }),
    ).toMatchObject({
      question: "이제 익절 기준을 몇 %로 정할까요?",
      // '익절 안 함'은 거부 칩(2026-08-10) — 익절을 안 쓰는 것도 정상 설계라 함께 나온다.
      suggestions: ["익절 10%", "익절 20%", "익절 30%", "익절 안 함"],
      missingCondition: { field: "take_profit" },
    });
  });

  it("종목 수를 직접 말한 전략(LLM provenance)의 허위 종목 오타 질문을 숨긴다", () => {
    expect(
      presentStrategyClarification({
        parsed: complete,
        backendQuestion:
          "입력하신 종목명을 인식하지 못했어요. 혹시 '코이즈'를 말씀하신 건가요?",
        gateOptions: { explicitFields: ["max_positions"] },
      }),
    ).toBeNull();
  });

  it("이미 정한 종목 수를 다시 묻지 않는다 — 판정은 explicit_fields만 본다", () => {
    expect(
      presentStrategyClarification({
        parsed: complete,
        backendQuestion: "상위 몇 종목을 선택할까요?",
        gateOptions: { explicitFields: ["max_positions"] },
      }),
    ).toBeNull();
    // 사용자가 말했다는 기록이 없으면 원문을 다시 읽지 않고 질문을 그대로 둔다(2026-11-12 원문 판정 제거).
    expect(
      presentStrategyClarification({
        parsed: complete,
        backendQuestion: "입력하신 종목명을 인식하지 못했어요. 혹시 '코이즈'를 말씀하신 건가요?",
      }),
    ).toMatchObject({ missingCondition: null });
  });

  it("진입 조건이 이미 있으면 종목 선택 되묻기를 숨긴다", () => {
    expect(
      presentStrategyClarification({
        parsed: complete,
        backendQuestion:
          "어떤 조건으로 종목을 선택할까요? (예: 재무 지표 기준, 기술적 신호, 기간 수익률 상위)",
      }),
    ).toBeNull();
  });

  it("실제 추가 확인 질문은 친절한 안내와 직접 입력 선택지를 유지한다", () => {
    expect(
      presentStrategyClarification({
        parsed: complete,
        backendQuestion: "여러 종목이 지정되었습니다. 어느 종목을 대상으로 할까요?",
        backendSuggestions: ["삼성전자", "SK하이닉스"],
      }),
    ).toEqual({
      question:
        "세부 조건이 빠져 있습니다. 여러 종목이 지정되었습니다. 어느 종목을 대상으로 할까요?",
      suggestions: ["삼성전자", "SK하이닉스"],
      missingCondition: null,
    });
  });
});

describe("shouldContinueWithSingleAssetBuilder", () => {
  it("지정 종목만 있고 진입 규칙이 없을 때만 전문 빌더를 계속 사용한다", () => {
    const parsed = {
      ...complete,
      target_symbols: ["005930"],
      fundamental_filters: [],
      entry_signals: [],
    };
    expect(shouldContinueWithSingleAssetBuilder(parsed)).toBe(true);
    expect(
      shouldContinueWithSingleAssetBuilder(
        { ...parsed, target_symbols: [] },
      ),
    ).toBe(false);
    expect(
      shouldContinueWithSingleAssetBuilder(
        { ...parsed, target_symbols: ["005930", "000660"] },
      ),
    ).toBe(false);
  });
});
