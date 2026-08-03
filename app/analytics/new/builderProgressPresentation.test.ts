import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  attachFieldStates,
  buildBuilderTurnPresentation,
  countProgress,
  progressStatusText,
} from "./builderProgressPresentation";

const themeParsed: ParsedSummary = {
  description: "모바일솔루션 관련주 투자 전략",
  universe: [],
  target_symbols: ["108860", "139670", "051160"],
  fundamental_filters: [],
  entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: null,
  initial_capital: null,
} as unknown as ParsedSummary;

describe("buildBuilderTurnPresentation 리밸런싱 표시 게이트", () => {
  it("다종목 지정(테마 유니버스)은 답하기 전까지 기본값 '설정 안 함'을 확정 표시하지 않는다", () => {
    // [회귀 2026-07-28 '모바일솔루션 관련주' 사고] 지정 종목이 있으면 리밸런싱을 '명시됨'으로
    // 간주해 질문 없이 요약 카드에 '리밸런싱: 설정 안 함'이 노출되던 버그.
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      explicitFields: ["universe"],
    });
    expect(
      presentation.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toBeUndefined();
  });

  it("사용자가 답하면(안 함 포함) 그 결정을 표시한다", () => {
    const declined = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      explicitFields: ["universe", "rebalancing"],
    });
    expect(
      declined.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "설정 안 함" });

    const monthly = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, rebalancing_period: "monthly" } as ParsedSummary,
      explicitFields: ["universe", "rebalancing"],
    });
    expect(
      monthly.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "매월" });
  });

  it("단독 종목(지정 1개)은 교체가 없어 기존대로 '설정 안 함'을 표시한다", () => {
    const single = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, target_symbols: ["005930"] } as ParsedSummary,
      explicitFields: ["universe"],
    });
    expect(
      single.summaryItems.find((item) => item.label === "리밸런싱"),
    ).toMatchObject({ value: "설정 안 함" });
  });
});

describe("buildBuilderTurnPresentation 지정 종목 배분 표시", () => {
  it("다종목 지정은 '최대 보유 N종목' 대신 실행 배분(균등 투자)을 표시한다", () => {
    // [2026-07-28 '모바일솔루션 관련주' 카드-실행 불일치] 지정 종목 모드는 변환기가
    // max_positions=지정 종목 수로 덮어쓰므로(FR-STR-068 ①) 기본값 '최대 보유 10종목'은
    // 실행과 다른 정보였다 — 파싱 카드와 동일한 FR-STR-068 ⑧ 표기로 통일.
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: themeParsed,
      explicitFields: ["universe"],
    });
    expect(
      presentation.summaryItems.find((item) => item.label === "최대 보유"),
    ).toBeUndefined();
    expect(
      presentation.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ value: "지정 종목 3개 균등 투자" });
    expect(
      presentation.progressItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ complete: true });
  });

  it("단독 종목(지정 1개)은 '단일 종목 집중 투자'를 표시한다", () => {
    const single = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: { ...themeParsed, target_symbols: ["005930"] } as ParsedSummary,
      explicitFields: ["universe"],
    });
    expect(
      single.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toMatchObject({ value: "단일 종목 집중 투자" });
  });

  it("유니버스 전략은 기존대로 명시된 최대 보유 종목 수를 표시한다", () => {
    const universe = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: {
        ...themeParsed,
        target_symbols: [],
        universe: ["KOSPI200"],
        max_positions: 5,
      } as ParsedSummary,
      explicitFields: ["universe", "max_positions"],
    });
    expect(
      universe.summaryItems.find((item) => item.label === "최대 보유"),
    ).toMatchObject({ value: "5종목" });
    expect(
      universe.summaryItems.find((item) => item.label === "포트폴리오"),
    ).toBeUndefined();
  });

  it("백엔드가 명시로 보고한 최대 보유는 요약·진행률에 반영한다", () => {
    // [회귀 2026-07-29 가치투자 예시 카드 사고] '최대 보유 종목은 10개'를 프론트 정규식이
    // 미탐해 요약에서 빠지고 진행률도 미체크였다. 이제 판정은 LLM 구조화 출력에서만 온다.
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: {
        ...themeParsed,
        target_symbols: [],
        universe: ["KOSPI"],
        max_positions: 10,
      } as ParsedSummary,
      explicitFields: ["universe", "max_positions"],
    });
    expect(
      presentation.summaryItems.find((item) => item.label === "최대 보유"),
    ).toMatchObject({ value: "10종목" });
    expect(
      presentation.progressItems.find((item) => item.label === "최대 보유"),
    ).toMatchObject({ complete: true });
  });
});

describe("신규 상장 유니버스 표시 (FR-STR-073)", () => {
  it("시장 라벨에 신규 상장 제한을 덧붙인다", () => {
    // [회귀] 2026-07-29: "코스피·코스닥 전체"만 보여 전 종목 대상으로 읽히던 문제.
    const presentation = buildBuilderTurnPresentation({
      state: {
        universe: "KOSPI_KOSDAQ",
        new_listing_only: true,
        listing_from: "2026-01-01",
        listing_to: "2026-12-31",
      },
      reply: "",
    });
    const target = presentation.summaryItems.find((item) => item.label === "유니버스");
    expect(target?.value).toBe("KOSPI·KOSDAQ 전체 · 2026년 상장");
  });

  it("제한이 없으면 시장 라벨만 남는다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: { universe: "KOSPI_KOSDAQ" },
      reply: "",
    });
    const target = presentation.summaryItems.find((item) => item.label === "유니버스");
    expect(target?.value).toBe("KOSPI·KOSDAQ 전체");
  });
});

describe("백테스트 기간 표시 — 명시 날짜 우선 (FR-STR-073)", () => {
  it("신규 상장 코호트로 창이 조정되면 상대 기간 라벨 대신 실제 창을 보여준다", () => {
    // [회귀] 2026-07-29: "2026년 신규 상장"인데 기본 5년 라벨이 남아 2022년부터로 읽혔다.
    const presentation = buildBuilderTurnPresentation({
      state: { universe: "KOSPI_KOSDAQ", new_listing_only: true },
      reply: "",
      parsed: {
        ...themeParsed,
        target_symbols: [],
        new_listing_only: true,
        listing_from: "2026-01-01",
        listing_to: "2026-12-31",
        backtest_period: "5y",
        backtest_start_date: "2026-01-01",
        backtest_end_date: null,
      },
    });
    const period = presentation.summaryItems.find((i) => i.label === "백테스트 기간");
    expect(period?.value).toBe("2026-01-01 ~ 현재");
    // [회귀] 창이 자동 확정됐는데 진행률 체크가 안 되던 사고 — 게이트와 같은 술어를 쓴다.
    const slot = presentation.progressItems.find((i) => i.label === "백테스트 기간");
    expect(slot?.complete).toBe(true);
  });
});

describe("손절 표시 — 항상 마이너스 부호 (2026-07-30)", () => {
  it("리스크 관리 요약은 손절을 '-8%'로, 익절은 부호 없이 표시한다", () => {
    // [회귀] 요약 카드가 '손절 8%'로만 표시해 방향을 알 수 없었다 — 매도 조건 라벨
    // ('손절 -8% 하락시 매도')과도 어긋났다.
    const presentation = buildBuilderTurnPresentation({
      state: { stop_loss_pct: 8, take_profit_pct: 30 },
      reply: "",
      parsed: null,
    });
    const risk = presentation.summaryItems.find((item) => item.label === "리스크 관리");
    expect(risk?.value).toBe("손절 -8% · 익절 30%");
  });

  it("트레일링 스탑도 하락 방향이라 '-10%'로 표시한다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: { stop_loss_pct: 8, take_profit_pct: 30, trailing_stop_pct: 10 },
      reply: "",
      parsed: null,
    });
    const risk = presentation.summaryItems.find((item) => item.label === "리스크 관리");
    expect(risk?.value).toBe("손절 -8% · 익절 30% · 트레일링 스탑 -10%");
  });
});

describe("attachFieldStates — 백엔드 두 상태 축 부착", () => {
  const items = [
    { label: "유니버스", complete: true },
    { label: "최대 보유", complete: true },
    { label: "리밸런싱", complete: true },
  ];

  it("슬롯 이름이 일치하면 두 축을 각각 붙인다", () => {
    expect(
      attachFieldStates(items, {
        유니버스: { value: "CONFIRMED", derived: "APPLICABLE" },
        리밸런싱: { value: "PROVISIONAL", derived: "NOT_APPLICABLE" },
      }),
    ).toEqual([
      { label: "유니버스", complete: true, valueStatus: "CONFIRMED", derivedStatus: "APPLICABLE" },
      { label: "최대 보유", complete: true },
      {
        label: "리밸런싱",
        complete: true,
        valueStatus: "PROVISIONAL",
        derivedStatus: "NOT_APPLICABLE",
      },
    ]);
  });

  it("카드가 상황에 따라 바꿔 다는 라벨도 슬롯 어휘로 되돌려 맞춘다", () => {
    // 지정 종목 전략에서 '최대 보유'는 '포트폴리오'로 표시된다.
    expect(
      attachFieldStates([{ label: "포트폴리오", complete: true }], {
        "최대 보유": { derived: "NOT_APPLICABLE" },
      }),
    ).toEqual([{ label: "포트폴리오", complete: true, derivedStatus: "NOT_APPLICABLE" }]);
  });

  it("상태 맵이 없으면 원본을 그대로 둔다(표시가 예전 동작으로 회귀)", () => {
    expect(attachFieldStates(items, null)).toBe(items);
    expect(attachFieldStates(items, undefined)).toBe(items);
  });

  it("맵에 없는 슬롯은 상태 없이 남는다", () => {
    expect(attachFieldStates(items, { 없는슬롯: { value: "CONFIRMED" } })).toEqual(items);
  });
});

describe("countProgress — '해당 없음'은 분모에서 뺀다", () => {
  it("해당 없음 칸은 분자·분모 양쪽에서 빠진다", () => {
    expect(
      countProgress([
        { label: "유니버스", complete: true, valueStatus: "CONFIRMED" },
        { label: "매수 조건", complete: false, valueStatus: "UNKNOWN" },
        { label: "리밸런싱", complete: true, derivedStatus: "NOT_APPLICABLE" },
      ]),
    ).toEqual({ completed: 1, total: 2 });
  });

  it("상태가 없으면 기존 동작 그대로 전부 센다", () => {
    expect(
      countProgress([
        { label: "유니버스", complete: true },
        { label: "매수 조건", complete: false },
      ]),
    ).toEqual({ completed: 1, total: 2 });
  });

  it("확인 필요(INVALID·CONFLICTED)는 분모에 남는다 — 해결해야 할 칸이다", () => {
    expect(
      countProgress([
        { label: "매수 조건", complete: true, derivedStatus: "CONFLICTED" },
        { label: "매도 조건", complete: true, derivedStatus: "INVALID" },
      ]),
    ).toEqual({ completed: 2, total: 2 });
  });
});

describe("progressStatusText — 두 축을 화면 문구 하나로", () => {
  it("파생 축이 값 축보다 앞선다 — 지금 못 쓰는 칸은 값이 확정이어도 손이 필요하다", () => {
    expect(
      progressStatusText({
        label: "매수 조건",
        complete: true,
        valueStatus: "CONFIRMED",
        derivedStatus: "INVALID",
      }),
    ).toBe("확인 필요");
    expect(
      progressStatusText({
        label: "리밸런싱",
        complete: true,
        valueStatus: "CONFIRMED",
        derivedStatus: "NOT_APPLICABLE",
      }),
    ).toBe("해당 없음");
  });

  it("성립하는 칸은 값 축이 문구를 정한다", () => {
    expect(
      progressStatusText({
        label: "최대 보유",
        complete: true,
        valueStatus: "PROVISIONAL",
        derivedStatus: "APPLICABLE",
      }),
    ).toBe("미확인");
    expect(
      progressStatusText({
        label: "최대 보유",
        complete: true,
        valueStatus: "CONFIRMED",
        derivedStatus: "APPLICABLE",
      }),
    ).toBeUndefined();
  });
});


describe("매도 조건 — 리스크 관리와 값을 중복하지 않는다 (2026-08-02)", () => {
  it("매도 조건은 지표 청산만, 손절·익절·보유 기간은 리스크 관리만 보여준다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: { stop_loss_pct: 8, take_profit_pct: 30, hold_period_days: 25 },
      reply: "",
      parsed: {
        ...themeParsed,
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
        stop_loss_pct: 8,
        take_profit_pct: 30,
        hold_period_days: 25,
      },
    });
    const exit = presentation.summaryItems.find((i) => i.label === "매도 조건");
    expect(exit?.value).toBe("MA 데드크로스");
    // 같은 값이 카드 안에서 두 번 읽히지 않는다.
    expect(exit?.value).not.toContain("손절");
    expect(exit?.value).not.toContain("익절");
    const risk = presentation.summaryItems.find((i) => i.label === "리스크 관리");
    expect(risk?.value).toBe("손절 -8% · 익절 30% · 25일 보유");
  });

  it("지표 청산이 없으면 매도 조건 항목 자체를 만들지 않는다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: { stop_loss_pct: 8 },
      reply: "",
      parsed: { ...themeParsed, exit_signals: [], stop_loss_pct: 8 },
    });
    expect(presentation.summaryItems.find((i) => i.label === "매도 조건")).toBeUndefined();
    expect(presentation.summaryItems.find((i) => i.label === "리스크 관리")?.value).toBe("손절 -8%");
  });
});

describe("값-대기 조건(pending_conditions) 요약 표시 — 2026-08-03 '당기순이익' 사고", () => {
  // [회귀] 값 미정 조건은 컴파일된 parsed에 없어(무단 확정 금지) 요약이 빈 전략으로
  // 보였다("첫 조건부터 하나씩") — 백엔드 pending_conditions 채널이 요약에 반영돼야 한다.
  const emptyParsed = {
    ...themeParsed,
    target_symbols: [],
    entry_signals: [],
    fundamental_filters: [],
  } as unknown as ParsedSummary;

  it("확정 조건이 하나도 없어도 값-대기 조건이 매수 조건 행으로 나타난다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: emptyParsed,
      pendingConditions: [
        { role: "entry", label: "순이익증가율", source_text: "당기순이익과" },
        { role: "entry", label: "영업이익률", source_text: "영업이익률이 높은" },
      ],
    });
    const entry = presentation.summaryItems.find((i) => i.label === "매수 조건");
    // 원문 표현과 다른 지표로 매핑된 조건('당기순이익' → 순이익증가율)은 치환을 고지한다.
    expect(entry?.value).toBe(
      "'당기순이익과' → 순이익증가율(값 미정) · 영업이익률(값 미정)",
    );
    expect(presentation.summaryItems.length).toBeGreaterThan(0);
  });

  it("확정 조건이 있으면 그 뒤에 값-대기 조건을 덧붙인다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: {
        ...emptyParsed,
        fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
      } as unknown as ParsedSummary,
      pendingConditions: [
        { role: "entry", label: "영업이익률", source_text: "영업이익률이 높은" },
      ],
    });
    const entry = presentation.summaryItems.find((i) => i.label === "매수 조건");
    expect(entry?.value).toContain("PER");
    expect(entry?.value).toContain("영업이익률(값 미정)");
  });

  it("괄호 병기 라벨(PER(주가수익비율))은 약칭이 원문에 있으면 치환 고지를 붙이지 않는다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: emptyParsed,
      pendingConditions: [
        { role: "entry", label: "PER(주가수익비율)", source_text: "PER 낮은" },
      ],
    });
    const entry = presentation.summaryItems.find((i) => i.label === "매수 조건");
    expect(entry?.value).toBe("PER(주가수익비율)(값 미정)");
  });

  it("청산 값-대기 조건은 매도 조건 행에 나타난다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: emptyParsed,
      pendingConditions: [
        { role: "exit", label: "RSI", source_text: "RSI 높으면 매도" },
      ],
    });
    const exit = presentation.summaryItems.find((i) => i.label === "매도 조건");
    expect(exit?.value).toBe("RSI(값 미정)");
  });

  it("pending_conditions가 없으면 기존 표시와 동일하다", () => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "질문",
      parsed: emptyParsed,
    });
    expect(presentation.summaryItems.find((i) => i.label === "매수 조건")).toBeUndefined();
  });
});
