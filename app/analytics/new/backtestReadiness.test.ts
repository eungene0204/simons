import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
  isBacktestReady,
  isClosedChoiceSlot,
  isSlotFilled,
  promptForSlot,
} from "./backtestReadiness";

const base: ParsedSummary = {
  description: "x",
  universe: ["KOSPI200"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "5y",
  initial_capital: 10_000_000,
};

describe("isBacktestReady", () => {
  it("유니버스 전략은 리밸런싱까지 있어야 실행 가능", () => {
    const withoutRebal = {
      ...base,
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };
    // 리밸런싱(none)이 없으면 유니버스 전략은 실행 불가
    expect(isBacktestReady(withoutRebal)).toBe(false);
    expect(isBacktestReady({ ...withoutRebal, rebalancing_period: "monthly" })).toBe(true);
  });

  it("리밸런싱 누락 안내에서 안 함을 선택할 수 있고 명시적 선택으로 인정한다", () => {
    const withoutRebal = {
      ...base,
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };

    expect(getNextMissingBacktestCondition(withoutRebal)).toMatchObject({
      field: "rebalancing",
      suggestions: [
        "매주 리밸런싱",
        "매월 리밸런싱",
        "분기마다 리밸런싱",
        "안 함",
      ],
    });
    expect(
      isBacktestReady(withoutRebal, { allowNoRebalancing: true }),
    ).toBe(true);
  });

  it("단독 종목은 리밸런싱 없이도(나머지 충족 시) 실행 가능", () => {
    expect(
      isBacktestReady({
        ...base,
        target_symbols: ["005930"],
        entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
        stop_loss_pct: 10,
        take_profit_pct: 20,
      }),
    ).toBe(true);
  });

  it("지정 종목(테마 자동 적용)이라도 매수 조건이 없으면 완성으로 판정하지 않는다", () => {
    // [버그 2026-07-25] 테마 유니버스가 target_symbols를 채우면 진입으로 인정돼 매수 조건
    // 질문이 생략되고 "모든 조건을 정했습니다"가 뜨던 사고 — 빈 진입은 엔진에서 0거래다.
    const themeParsed: ParsedSummary = {
      ...base,
      target_symbols: ["352820", "035900", "041510"],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 15,
      take_profit_pct: 30,
      initial_capital: 50_000_000,
    };
    const options = {
      requireExplicitConfiguration: true,
      explicitFields: ["universe", "max_positions", "backtest_period", "initial_capital"],
    };
    expect(getNextMissingBacktestCondition(themeParsed, options)).toMatchObject({
      field: "entry",
    });
    expect(isBacktestReady(themeParsed, options)).toBe(false);
    expect(
      isBacktestReady(
        {
          ...themeParsed,
          entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
          rebalancing_period: "monthly",
        },
        { ...options, explicitFields: [...options.explicitFields, "rebalancing"] },
      ),
    ).toBe(true);
  });

  it("지정 종목이 여러 개(테마 유니버스)면 리밸런싱을 묻는다 — 기본값 확정 금지", () => {
    // [회귀 2026-07-28 '모바일솔루션 관련주' 사고] '지정 종목 존재=단독 종목'으로 판정해
    // 리밸런싱 질문이 생략되고 기본값 '설정 안 함'으로 조용히 확정되던 버그.
    const themeParsed: ParsedSummary = {
      ...base,
      target_symbols: ["108860", "139670", "051160"],
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };
    const options = {
      requireExplicitConfiguration: true,
      explicitFields: ["universe", "max_positions", "backtest_period", "initial_capital"],
    };
    expect(getNextMissingBacktestCondition(themeParsed, options)).toMatchObject({
      field: "rebalancing",
    });
    // '안 함' 선택(allowNoRebalancing)도 사용자의 결정으로 인정한다.
    expect(
      isBacktestReady(themeParsed, {
        ...options,
        allowNoRebalancing: true,
      }),
    ).toBe(true);
    // 단독 종목(1개)은 교체가 없어 기존대로 묻지 않는다.
    expect(
      isBacktestReady({ ...themeParsed, target_symbols: ["005930"] }, options),
    ).toBe(true);
  });

  it("손절·익절이 없으면 실행 불가(버튼 숨김)", () => {
    expect(
      isBacktestReady({
        ...base,
        entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      }),
    ).toBe(false);
  });

  it("단일 종목만 지정하고 나머지 조건이 없으면 실행 불가", () => {
    expect(isBacktestReady({ ...base, target_symbols: ["005930"] })).toBe(false);
  });

  it("모멘텀 랭킹+정기 리밸런싱은 진입·청산으로 인정하되 손절·익절이 있어야 실행 가능", () => {
    const momentum: ParsedSummary = {
      ...base,
      ranking_metric: "return",
      rebalancing_period: "monthly",
    };
    expect(isBacktestReady(momentum)).toBe(false);
    expect(isBacktestReady({ ...momentum, stop_loss_pct: 10, take_profit_pct: 20 })).toBe(true);
  });

  it("parsed가 없으면 실행 불가", () => {
    expect(isBacktestReady(undefined)).toBe(false);
  });
});

describe("explicit_fields 기반 되묻기 게이트 (원문 정규식 폐지)", () => {
  // [2026-07-29 계약 전환] "사용자가 말했나"는 인터프리터 LLM의 구조화 출력에서만 온다.
  // 프론트가 원문을 정규식으로 재분석하던 hasExplicit* 5종은 삭제됐고, 그 정규식이 낸
  // 양방향 사고(오탐/미탐)는 구조적으로 재발할 수 없다 — 이 레이어는 텍스트를 읽지 않는다.
  const complete: ParsedSummary = {
    ...base,
    entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
    exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
    rebalancing_period: "monthly",
    stop_loss_pct: 10,
    take_profit_pct: 20,
  };
  const allFields = [
    "universe",
    "max_positions",
    "rebalancing",
    "backtest_period",
    "initial_capital",
  ];

  it("백엔드가 명시로 보고한 필드만 충족으로 인정한다", () => {
    expect(
      isBacktestReady(complete, {
        requireExplicitConfiguration: true,
        explicitFields: allFields,
      }),
    ).toBe(true);
  });

  it("값이 있어도(기본값 물질화) 명시 목록에 없으면 되묻는다", () => {
    // max_positions=10은 시스템 기본값일 수 있다 — 값의 존재는 명시의 증거가 아니다.
    expect(
      getNextMissingBacktestCondition(complete, {
        requireExplicitConfiguration: true,
        explicitFields: allFields.filter((f) => f !== "max_positions"),
      }),
    ).toMatchObject({ field: "max_positions" });
  });

  it("게이트 판정은 사용자 원문 문구에 영향받지 않는다", () => {
    // 과거 오탐: '거래대금 20억 원'을 초기 자본 명시로 오인 / 미탐: '보유 종목은 10개'.
    // 이제 두 문장 모두 게이트에 전달되지 않으므로 판정에 관여할 수 없다.
    const withoutCapital = {
      requireExplicitConfiguration: true,
      explicitFields: allFields.filter((f) => f !== "initial_capital"),
    };
    expect(getNextMissingBacktestCondition(complete, withoutCapital)).toMatchObject({
      field: "initial_capital",
    });
    expect(
      isBacktestReady(complete, {
        ...withoutCapital,
        explicitFields: allFields,
      }),
    ).toBe(true);
  });

  it("유니버스만 선택지가 닫힌 슬롯이다 — 나머지는 자유 입력을 연다", () => {
    expect(isClosedChoiceSlot("universe")).toBe(true);
    for (const field of ["entry", "exit", "max_positions", "rebalancing",
      "stop_loss", "take_profit", "backtest_period", "initial_capital"]) {
      expect(isClosedChoiceSlot(field)).toBe(false);
    }
    expect(isClosedChoiceSlot(undefined)).toBe(false);
  });

  it("지정 종목은 그 자체로 유니버스 명시다", () => {
    const single = { ...complete, target_symbols: ["005930"] };
    expect(
      isBacktestReady(single, {
        requireExplicitConfiguration: true,
        explicitFields: allFields.filter((f) => f !== "universe"),
      }),
    ).toBe(true);
  });
});

describe("분위 그룹 전략의 최대 보유 되묻기 (FR-BT-060b)", () => {
  const quantileBase: ParsedSummary = {
    ...base,
    universe: ["KOSPI", "KOSDAQ"],
    ranking_metric: "per",
    ranking_direction: "bottom",
    ranking_quantile_groups: 10,
    rebalancing_period: "quarterly",
  } as ParsedSummary;
  const options = {
    explicitFields: ["universe", "rebalancing", "backtest_period", "initial_capital"],
    requireExplicitConfiguration: true,
  };

  it("cap 미답변이면 전용 질문·칩(그룹당 10종목~)으로 묻는다", () => {
    const next = getNextMissingBacktestCondition(quantileBase, options);
    expect(next?.field).toBe("max_positions");
    expect(next?.question).toContain("분위 그룹");
    expect(next?.suggestions).toEqual(["그룹당 10종목", "그룹당 20종목", "그룹당 30종목"]);
  });

  it("cap을 답하면 provenance 없이도 충족된다(물질화 기본값 없는 필드)", () => {
    const answered = { ...quantileBase, ranking_group_cap: 10 } as ParsedSummary;
    const next = getNextMissingBacktestCondition(answered, options);
    expect(next?.field).not.toBe("max_positions");
  });

  it("일반 전략은 기존 질문·칩 그대로다", () => {
    const next = getNextMissingBacktestCondition(
      { ...base, rebalancing_period: "monthly" } as ParsedSummary,
      { explicitFields: ["universe", "rebalancing", "backtest_period", "initial_capital"],
        requireExplicitConfiguration: true },
    );
    if (next?.field === "max_positions") {
      expect(next.suggestions).toEqual(["최대 5종목", "최대 10종목", "최대 20종목"]);
    }
  });
});

// 손절·익절 '안 함'(2026-08-10) — 거부는 값이 아니라 목록으로 온다(백엔드 declined_fields).
describe("손절·익절 '안 함' 거부", () => {
  const readyExceptRisk: ParsedSummary = {
    ...base,
    universe: ["KOSPI"],
    entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
    exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
    rebalancing_period: "monthly",
    max_positions: 10,
    backtest_period: "5y",
    initial_capital: 10_000_000,
  };
  const options = {
    requireExplicitConfiguration: true,
    explicitFields: [
      "universe", "max_positions", "rebalancing", "backtest_period", "initial_capital",
    ],
  };

  it("거부 전에는 손절을 묻고, 거부하면 더 묻지 않는다", () => {
    expect(getNextMissingBacktestCondition(readyExceptRisk, options)).toMatchObject({
      field: "stop_loss",
    });
    expect(
      isBacktestReady(readyExceptRisk, {
        ...options,
        declinedFields: ["stop_loss", "take_profit"],
      }),
    ).toBe(true);
  });

  it("한쪽만 거부하면 나머지는 계속 묻는다", () => {
    expect(
      getNextMissingBacktestCondition(readyExceptRisk, {
        ...options,
        declinedFields: ["stop_loss"],
      }),
    ).toMatchObject({ field: "take_profit" });
  });

  it("거부 뒤에 값이 들어오면 값이 이긴다(백엔드와 같은 순서)", () => {
    const withStopLoss = { ...readyExceptRisk, stop_loss_pct: 10 };
    expect(
      isSlotFilled("stop_loss", withStopLoss, { ...options, declinedFields: ["stop_loss"] }),
    ).toBe(true);
  });

  it("손절·익절 질문에 '안 함' 선택지가 있다", () => {
    for (const field of ["stop_loss", "take_profit"] as const) {
      expect(promptForSlot(field).suggestions).toContain("안 함");
    }
  });
});
