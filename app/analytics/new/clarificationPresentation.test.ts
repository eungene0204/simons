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
  stop_loss_pct: 10,
  take_profit_pct: 20,
  backtest_period: "5y",
  initial_capital: 10_000_000,
};

describe("presentStrategyClarification", () => {
  it("백엔드 질문보다 파싱 결과의 다음 누락 조건을 우선한다", () => {
    expect(
      presentStrategyClarification({
        prompt: "PBR 1 이하, 손절 10%",
        parsed: { ...complete, take_profit_pct: null },
        backendQuestion: "익절 — 목표 수익 비율을 정해주세요",
        backendSuggestions: ["익절 20%"],
      }),
    ).toMatchObject({
      question: "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      suggestions: ["익절 10%", "익절 20%", "익절 30%"],
      missingCondition: { field: "take_profit" },
    });
  });

  it("완성된 포트폴리오 전략의 허위 종목 오타 질문을 숨긴다", () => {
    expect(
      presentStrategyClarification({
        prompt: "KOSPI에서 골든크로스 전략을 최대 10종목으로 구성해 주세요.",
        parsed: complete,
        backendQuestion:
          "입력하신 종목명을 인식하지 못했어요. 혹시 '코이즈'를 말씀하신 건가요?",
      }),
    ).toBeNull();
  });

  it("원문에 없는 지표나 이미 정한 종목 수를 다시 묻지 않는다", () => {
    expect(
      presentStrategyClarification({
        prompt: "PBR 1 이하 종목을 10종목으로 구성해 주세요.",
        parsed: complete,
        backendQuestion: "청산 조건의 배당수익률 기준값을 얼마로 할까요?",
      }),
    ).toBeNull();
    expect(
      presentStrategyClarification({
        prompt: "상대강도 순위로 전체 포트폴리오는 10종목으로 제한해 주세요.",
        parsed: complete,
        backendQuestion: "상위 몇 종목을 선택할까요?",
      }),
    ).toBeNull();
  });

  it("진입 조건이 이미 있으면 종목 선택 되묻기를 숨긴다", () => {
    expect(
      presentStrategyClarification({
        prompt:
          "KOSPI 흑자 기업 매수, 손절 10% 익절 30%, 매월 리밸런싱, 최근 5년, 3000만원",
        parsed: complete,
        backendQuestion:
          "어떤 조건으로 종목을 선택할까요? (예: 재무 지표 기준, 기술적 신호, 기간 수익률 상위)",
      }),
    ).toBeNull();
  });

  it("실제 추가 확인 질문은 친절한 안내와 직접 입력 선택지를 유지한다", () => {
    expect(
      presentStrategyClarification({
        prompt: "삼성전자와 SK하이닉스 중 하나로 설정해 주세요.",
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
