import { describe, expect, it } from "vitest";

import { applyDeterministicConditionChoice } from "./deterministicConditionFlow";
import type { ParsedSummary } from "./strategySummary";

// 칩 기간 명시화(2026-07-26): 크로스 칩은 라벨과 값 모두 기간을 명시한다.
// 값은 엔진 실효 기본값(5/20)과 동일해 백테스트 결과는 불변이고, 기간 없는 신호가
// 요약 카드에 드러나지 않은 채 저장되던 불투명성(제주반도체 사고의 씨앗)을 없앤다.

const parsed = {} as ParsedSummary;

describe("기간 명시 크로스 칩", () => {
  it("골든크로스 칩은 5/20 기간을 명시해 진입 신호를 만든다", () => {
    const result = applyDeterministicConditionChoice({
      parsed,
      condition: { field: "entry", question: "", suggestions: [] },
      choice: "골든크로스(5일/20일) 발생 시 매수",
    });
    expect(result?.parsed.entry_signals).toEqual([
      {
        indicator: "ma_crossover",
        signal_type: "buy",
        short_period: 5,
        long_period: 20,
      },
    ]);
  });

  it("데드크로스 칩은 5/20 기간을 명시해 청산 신호를 만든다", () => {
    const result = applyDeterministicConditionChoice({
      parsed,
      condition: { field: "exit", question: "", suggestions: [] },
      choice: "데드크로스(5일/20일) 발생 시 매도",
    });
    expect(result?.parsed.exit_signals).toEqual([
      {
        indicator: "ma_crossover",
        signal_type: "sell",
        short_period: 5,
        long_period: 20,
      },
    ]);
  });

  it("기간 없는 구 라벨은 더 이상 매핑되지 않는다(반쪽 갱신 방지)", () => {
    for (const [field, choice] of [
      ["entry", "골든크로스 발생 시 매수"],
      ["exit", "데드크로스 발생 시 매도"],
    ] as const) {
      expect(
        applyDeterministicConditionChoice({
          parsed,
          condition: { field, question: "", suggestions: [] },
          choice,
        }),
      ).toBeNull();
    }
  });
});

describe("분위 그룹 전략의 그룹당 상한 칩 (FR-BT-060b)", () => {
  it("'그룹당 10종목' 답변이 그룹당 상한과 종목 수를 함께 채운다", () => {
    const quantileParsed = {
      ranking_quantile_groups: 10,
      max_positions: 10,
    } as unknown as ParsedSummary;
    const result = applyDeterministicConditionChoice({
      parsed: quantileParsed,
      condition: { field: "max_positions", question: "", suggestions: [] },
      choice: "그룹당 10종목",
    });
    expect(result?.parsed.ranking_group_cap).toBe(10);
    expect(result?.parsed.max_positions).toBe(10);
  });

  it("일반 전략의 종목 수 답변은 그룹당 상한을 만들지 않는다", () => {
    const result = applyDeterministicConditionChoice({
      parsed,
      condition: { field: "max_positions", question: "", suggestions: [] },
      choice: "최대 10종목",
    });
    expect(result?.parsed.max_positions).toBe(10);
    expect(result?.parsed.ranking_group_cap).toBeUndefined();
  });
});
