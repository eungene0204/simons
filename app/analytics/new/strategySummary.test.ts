import { describe, expect, it } from "vitest";
import {
  buildStrategySummary,
  buildStrategySummaryFromRequest,
  buildStrategySummaryChips,
  buildStrategySummaryFromDsl,
  formatFundamentalFilter,
  formatInitialCapital,
  FUNDAMENTAL_FILTER_SECTION_LABEL,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  getSignalLabel,
  hasBuyCriteria,
  isRawSymbolUniverseName,
  resolveUniverseDisplayName,
  type ParsedSummary,
} from "./strategySummary";

const baseParsed: ParsedSummary = {
  description: "테스트 전략",
  universe: ["KOSPI"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

describe("getSignalLabel — 크로스 방향 구체화", () => {
  it("이동평균 크로스를 방향별 골든/데드크로스로 라벨링한다", () => {
    expect(getSignalLabel({ indicator: "ma_crossover", signal_type: "buy" }, "entry")).toBe(
      "MA 골든크로스"
    );
    expect(getSignalLabel({ indicator: "ma_crossover", signal_type: "sell" }, "exit")).toBe(
      "MA 데드크로스"
    );
  });

  it("signal_type이 없으면 진입은 골든, 청산은 데드로 본다", () => {
    expect(getSignalLabel({ indicator: "ma_crossover" }, "entry")).toBe("MA 골든크로스");
    expect(getSignalLabel({ indicator: "ma_crossover" }, "exit")).toBe("MA 데드크로스");
  });

  it("EMA·MACD 크로스도 방향별로 구체화한다", () => {
    expect(getSignalLabel({ indicator: "ema", signal_type: "buy" }, "entry")).toBe(
      "EMA 골든크로스"
    );
    expect(getSignalLabel({ indicator: "macd", signal_type: "sell" }, "exit")).toBe(
      "MACD 데드크로스"
    );
  });

  it("MACD 제로선 모드는 제로선 돌파로 라벨링한다", () => {
    expect(getSignalLabel({ indicator: "macd", signal_type: "buy", mode: "zero" }, "entry")).toBe(
      "MACD 제로선 상향 돌파"
    );
    expect(getSignalLabel({ indicator: "macd", signal_type: "sell", mode: "zero" }, "exit")).toBe(
      "MACD 제로선 하향 돌파"
    );
  });

  it("크로스가 아닌 지표는 기존 라벨을 유지한다", () => {
    expect(getSignalLabel({ indicator: "rsi", signal_type: "buy" }, "entry")).toBe("RSI");
  });
});

describe("hasBuyCriteria", () => {
  it("유니버스·최대 종목만 있고 매수 기준이 없으면 false", () => {
    expect(hasBuyCriteria(baseParsed)).toBe(false);
  });

  it("재무 필터가 있으면 true", () => {
    expect(
      hasBuyCriteria({
        ...baseParsed,
        fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
      })
    ).toBe(true);
  });

  it("기술적 진입 신호가 있으면 true", () => {
    expect(
      hasBuyCriteria({
        ...baseParsed,
        entry_signals: [{ indicator: "ma_crossover" }],
      })
    ).toBe(true);
  });

  it("랭킹(상대강도) 선정이 있으면 true", () => {
    expect(
      hasBuyCriteria({ ...baseParsed, ranking_metric: "return" })
    ).toBe(true);
  });

  it("청산/리스크 설정만 있고 매수 기준이 없으면 false", () => {
    expect(
      hasBuyCriteria({
        ...baseParsed,
        exit_signals: [{ indicator: "rsi" }],
        stop_loss_pct: 5,
        take_profit_pct: 10,
      })
    ).toBe(false);
  });

  it("null/undefined는 false", () => {
    expect(hasBuyCriteria(null)).toBe(false);
    expect(hasBuyCriteria(undefined)).toBe(false);
  });
});

describe("strategySummary", () => {
  it("재무 조건 섹션도 UI에서는 진입 신호로 표시한다", () => {
    expect(FUNDAMENTAL_FILTER_SECTION_LABEL).toBe("진입 신호");
  });

  it("시총 배지는 원 단위 숫자를 한글 단위(억/조)로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 10_000_000_000 }))
      .toBe("시총 >= 100억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 1_000_000_000_000 }))
      .toBe("시총 >= 1조");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 300_000_000_000 }))
      .toBe("시총 >= 3,000억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: "<=", value: 1_500_000_000_000 }))
      .toBe("시총 <= 1조 5,000억");
  });

  it("시총 외 지표(PER 등)는 숫자를 그대로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "per", operator: "<=", value: 10 })).toBe("PER <= 10");
    expect(formatFundamentalFilter({ metric: "roe_or_gpa", operator: ">=", value: 15 })).toBe("ROE >= 15");
  });

  it("거래대금 배지는 억 단위 숫자에 '억'을 붙여 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "trading_value", operator: ">=", value: 50 }))
      .toBe("거래대금 >= 50억");
    expect(formatFundamentalFilter({ metric: "trading_value", operator: ">=", value: 1000 }))
      .toBe("거래대금 >= 1,000억");
  });

  it("초기자금 배지는 1억 이상이면 한글 단위(억/조)로 표시한다", () => {
    expect(formatInitialCapital(5_000_000_000)).toBe("50억원");
    expect(formatInitialCapital(1_000_000_000_000)).toBe("1조원");
  });

  it("초기자금 배지는 1억 미만이면 콤마 포함 원 단위로 표시한다", () => {
    expect(formatInitialCapital(10_000_000)).toBe("10,000,000원");
  });

  it("실행 심볼 수가 KOSPI 규모면 KOSPI200 대신 KOSPI로 표시한다", () => {
    const labels = getDisplayUniverseLabels(
      { ...baseParsed, universe: ["KOSPI200"] },
      { symbols: Array.from({ length: 800 }, (_, index) => `${index}`) }
    );

    expect(labels).toEqual(["KOSPI"]);
  });

  it("기술적 청산 신호와 리스크 레이블을 함께 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "cci" }],
      take_profit_pct: 10,
    });

    expect(labels).toEqual(["CCI", "익절 10% 이상 수익시 매도"]);
  });

  it("손절은 청산 신호 라벨에도 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 8,
    });

    expect(labels).toEqual(["MA 데드크로스", "손절 -8% 하락시 매도"]);
  });

  it("트레일링 스탑과 최대 보유기간도 청산 신호 라벨에 포함한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      trailing_stop_pct: 10,
      hold_period_days: 20,
    });

    expect(labels).toEqual([
      "트레일링 스탑 -10% 하락시 매도",
      "최대 20일 보유 후 매도",
    ]);
  });

  it("sell 문맥의 AI 신호는 청산 요약에서 하락 예측으로 표시한다", () => {
    const labels = getDisplayExitLabels({
      ...baseParsed,
      exit_signals: [{ indicator: "ai_model", signal_type: "sell" }],
    });

    expect(labels).toEqual(["AI 하락 예측"]);
  });

  it("익절과 손절이 모두 있으면 전략 요약에도 같은 문구를 반영한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      stop_loss_pct: 7,
      take_profit_pct: 10,
    });

    expect(summary?.exitBlocks).toEqual([
      "손절 -7% 하락시 매도",
      "익절 10% 이상 수익시 매도",
    ]);
    expect(summary?.riskText).toBe("손절 7%, 익절 10%");
  });

  it("재무 필터 단독 전략도 진입 신호(entryBlocks)에 필터를 포함한다 (청산 배지 누출 방지)", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
      max_positions: 8,
      hold_period_days: 126,
      stop_loss_pct: 12,
    });

    // 진입 신호는 PBR 필터만 — 손절/보유기간 청산 배지가 섞이면 안 된다.
    expect(summary?.entryBlocks).toEqual(["PBR <= 1"]);
    expect(summary?.exitBlocks).toEqual([
      "손절 -12% 하락시 매도",
      "최대 126일 보유 후 매도",
    ]);
    // entryBlocks가 비지 않으므로 결과 화면이 blockNames 폴백을 쓰지 않는다.
    expect(summary?.entryBlocks).not.toContain("손절 -12% 하락시 매도");
    expect(summary?.entryBlocks).not.toContain("최대 126일 보유 후 매도");
  });

  it("모멘텀 랭킹(수익률 상위) 전략은 진입 신호 배지에 랭킹 레이블을 포함한다", () => {
    // 진입 조건 블록 없이 ranking_metric만 있는 순수 모멘텀 전략 — 엔진은 '선정=진입'으로 동작한다.
    // 배지에서 빠지면 진입 신호가 사라진 것처럼 보이므로 백테스트 요약에도 함께 노출돼야 한다.
    const summary = buildStrategySummary({
      ...baseParsed,
      ranking_metric: "return",
      ranking_lookback_days: 21,
    });

    expect(summary?.entryBlocks).toEqual(["21일 수익률 상위"]);
  });

  it("리스크 기반 청산이 없으면 기존 기술적 청산 레이블을 유지한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      exit_signals: [{ indicator: "cci" }],
    });

    expect(summary?.exitBlocks).toEqual(["CCI"]);
  });

  it("DSL 전략에서도 생성 모달용 요약 칩 정보를 만든다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-1",
      name: "테스트 전략",
      description: "사용자 프롬프트 원문",
      version: "1",
      universe: {
        id: "kospi",
        filters: {},
      },
      entry: {
        conditions: [{ id: "ma_crossover", type: "indicator", params: {} }],
      },
      exit: {
        conditions: [],
      },
      risk: {
        position_size_pct: 20,
        max_positions: 8,
        stop_loss_pct: 12,
        take_profit_pct: 10,
        max_holding_days: 182,
      },
      created_at: "",
      updated_at: "",
    });

    expect(summary?.universeName).toBe("KOSPI");
    expect(summary?.entryBlocks).toEqual(["MA 크로스"]);
    expect(summary?.blockNames).toContain("MA 크로스");
    expect(summary?.exitBlocks).toEqual([
      "손절 -12% 하락시 매도",
      "익절 10% 이상 수익시 매도",
      "최대 182일 보유 후 매도",
    ]);
    expect(summary?.positionText).toBe("포지션/비중 최대 8종목 · 182일 보유");
    expect(summary?.riskText).toBe("손절 12%, 익절 10%");
  });

  it("legacy 전략은 description에서 유니버스를 추론한다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-legacy",
      name: "PBR전략",
      description: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 고릅니다.",
      version: "1",
      universe: "" as any,
      entry: {
        conditions: [],
      },
      exit: {
        conditions: [],
      },
      risk: {
        position_size_pct: 20,
        max_positions: 8,
      },
      created_at: "",
      updated_at: "",
      symbols: Array.from({ length: 700 }, (_, index) => `${index}`),
    } as any);

    expect(summary?.universeName).toBe("KOSPI");
  });

  it("universe가 심볼 CSV로 저장돼도 description에서 유니버스 라벨을 복원한다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-csv-universe",
      name: "골든크로스",
      description:
        "KOSPI 종목 중 골든크로스가 나오면 매수하고 데드크로스가 나오면 매도. 최대 10종목, 손절 -8%.",
      version: "1",
      universe: "000020,000040,000050" as any,
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: { max_positions: 10, stop_loss_pct: 8 },
      created_at: "",
      updated_at: "",
    } as any);

    expect(summary?.universeName).toBe("KOSPI");
  });

  it("저장된 parsed 형태 전략에서도 필터, 포지션, 보유기간, 손절 배지를 복원한다", () => {
    const summary = buildStrategySummaryFromDsl({
      id: "strategy-parsed",
      name: "저PBR 대형주",
      description: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고 최소 6개월 보유, -12% 손절",
      version: "1",
      universe: ["KOSPI"],
      fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
      entry_signals: [],
      exit_signals: [],
      max_positions: 8,
      hold_period_days: 182,
      stop_loss_pct: 12,
      risk: {} as any,
      entry: { conditions: [] },
      exit: { conditions: [] },
      created_at: "",
      updated_at: "",
    } as any);

    expect(summary?.universeName).toBe("KOSPI");
    expect(summary?.entryBlocks).toEqual(["PBR <= 1"]);
    expect(summary?.exitBlocks).toContain("최대 182일 보유 후 매도");
    expect(summary?.exitBlocks).toContain("손절 -12% 하락시 매도");
    expect(summary?.positionText).toBe("포지션/비중 최대 8종목 · 182일 보유");
    expect(summary?.riskText).toBe("손절 12%");
  });

  it("심볼 CSV는 운용 전략 유니버스 배지로 표시하지 않는다", () => {
    const chips = buildStrategySummaryChips({
      universeName: "000020,000040,000050",
      entryBlocks: ["PBR <= 1"],
      exitBlocks: ["손절 -12% 하락시 매도"],
      positionText: "최대 8종목 · 126일 보유",
      riskText: "손절 12%",
    });

    expect(chips).not.toContain("유니버스 000020,000040,000050");
    expect(chips).toEqual([
      "PBR <= 1",
      "손절 -12% 하락시 매도",
      "최대 8종목 · 126일 보유",
      "리스크 관리 손절 12%",
    ]);
  });

  it("심볼 CSV 유니버스명은 raw 심볼로 판별한다 (프롬프트 배지 가드용)", () => {
    expect(isRawSymbolUniverseName("000020,000040,000050")).toBe(true);
    expect(isRawSymbolUniverseName("000020, 000040, 000050")).toBe(true);
    expect(isRawSymbolUniverseName("KOSPI")).toBe(false);
    expect(isRawSymbolUniverseName("KOSPI 200")).toBe(false);
    expect(isRawSymbolUniverseName("")).toBe(false);
  });

  it("심볼 CSV 유니버스명은 프롬프트에서 라벨을 복원해 표시한다", () => {
    expect(
      resolveUniverseDisplayName(
        "000020,000040,000050",
        "KOSPI 종목 중 골든크로스가 나오면 매수"
      )
    ).toBe("KOSPI");
    expect(
      resolveUniverseDisplayName("000020,000040,000050", "KOSDAQ 신고가 돌파")
    ).toBe("KOSDAQ");
  });

  it("실제 라벨은 그대로 두고, 라벨을 복원할 수 없으면 null", () => {
    expect(resolveUniverseDisplayName("KOSPI", "프롬프트")).toBe("KOSPI");
    expect(resolveUniverseDisplayName("KOSPI 200", null)).toBe("KOSPI 200");
    expect(resolveUniverseDisplayName("000020,000040", "유니버스 언급 없음")).toBeNull();
    expect(resolveUniverseDisplayName("미정", "유니버스 언급 없음")).toBeNull();
  });
});

describe("buildStrategySummaryFromRequest (실행된 요청 기반 배지)", () => {
  it("모멘텀 랭킹 요청은 entry.conditions가 비어도 진입 신호로 랭킹을 노출한다", () => {
    // 엔진은 risk.ranking_metric을 '선정=진입'으로 실행하므로 진입 배지에 나와야 한다.
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: {
        ranking_metric: "return",
        ranking_lookback_days: 21,
        max_positions: 5,
        rebalancing_period: "monthly",
        stop_loss_pct: 10,
        take_profit_pct: 20,
      },
    });

    expect(summary?.universeName).toBe("KOSPI");
    expect(summary?.entryBlocks).toEqual(["21일 수익률 상위"]);
    expect(summary?.exitBlocks).toEqual([
      "손절 -10% 하락시 매도",
      "익절 20% 이상 수익시 매도",
    ]);
    expect(summary?.positionText).toBe("최대 5종목");
    expect(summary?.rebalancingText).toBe("매월 리밸런싱");
    expect(summary?.riskText).toBe("손절 10%, 익절 20%");
  });

  it("랭킹·진입 조건이 모두 없는 요청은 진입 배지를 비워 0거래와 일관되게 표시한다", () => {
    // 실행된 요청에 진입이 없으면 배지도 비어야 한다 — 표시가 실행을 정직하게 반영(거짓 배지 금지).
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: { max_positions: 5, stop_loss_pct: 10 },
    });

    expect(summary?.entryBlocks).toEqual([]);
  });

  it("기술적 진입 조건은 한국어 레이블로 진입 배지에 들어간다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kosdaq",
      entry: { conditions: [{ type: "indicator", id: "ma_crossover", params: {} }] },
      exit: { conditions: [] },
      risk: { max_positions: 10 },
    });

    expect(summary?.universeName).toBe("KOSDAQ");
    expect(summary?.entryBlocks).toEqual(["MA 크로스"]);
  });

  it("요청이 없으면 undefined를 반환한다", () => {
    expect(buildStrategySummaryFromRequest(null)).toBeUndefined();
  });
});
