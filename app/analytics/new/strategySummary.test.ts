import { describe, expect, it } from "vitest";
import {
  buildStrategySummary,
  buildStrategySummaryFromRequest,
  buildStrategySummaryChips,
  buildStrategySummaryGroups,
  buildStrategySummaryFromDsl,
  explicitWindowSpanLabel,
  formatBacktestPeriodLabel,
  formatFundamentalFilter,
  formatInitialCapital,
  FUNDAMENTAL_FILTER_SECTION_LABEL,
  getDisplayExitLabels,
  formatNewListingLabel,
  getDisplayUniverseLabels,
  getSignalExitLabels,
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

  it("RSI 임계값 비교는 operator/value가 있으면 구체적인 임계값을 함께 표기한다", () => {
    expect(
      getSignalLabel({ indicator: "rsi", signal_type: "buy", operator: ">=", value: 50 }, "entry")
    ).toBe("RSI 50 이상");
    expect(
      getSignalLabel({ indicator: "rsi", signal_type: "sell", operator: "<=", value: 45 }, "exit")
    ).toBe("RSI 45 이하");
    // operator/value가 없으면 기존대로 "RSI"만 노출한다.
    expect(getSignalLabel({ indicator: "rsi", signal_type: "buy" }, "entry")).toBe("RSI");
  });

  it("RSI 반등(rebound)은 임계선 재돌파를 상향 반등/하향 반전으로 표기한다", () => {
    expect(
      getSignalLabel({ indicator: "rsi", signal_type: "buy", mode: "rebound", value: 30 }, "entry")
    ).toBe("RSI 30 상향 반등");
    expect(
      getSignalLabel({ indicator: "rsi", signal_type: "sell", mode: "rebound", value: 70 }, "exit")
    ).toBe("RSI 70 하향 반전");
    // value가 없으면 진입=30 / 청산=70 기본값을 쓴다.
    expect(getSignalLabel({ indicator: "rsi", mode: "rebound" }, "entry")).toBe("RSI 30 상향 반등");
    expect(getSignalLabel({ indicator: "rsi", mode: "rebound" }, "exit")).toBe("RSI 70 하향 반전");
  });

  it("브레이크아웃은 기준 기간에 따라 신고가/고점 돌파로 구체화한다", () => {
    // 252일(≈52주) → "52주 신고가 돌파" (사용자가 '52주 신고가'를 명시했는데 배지가
    // 일반 '브레이크아웃'으로만 보이던 문제 보정).
    expect(
      getSignalLabel({ indicator: "breakout", signal_type: "buy", lookback_period: 252 }, "entry")
    ).toBe("52주 신고가 돌파");
    expect(
      getSignalLabel({ indicator: "breakout", signal_type: "sell", lookback_period: 252 }, "exit")
    ).toBe("52주 신저가 이탈");
    // 그 밖의 N일은 고점 돌파/저점 이탈로 표기한다.
    expect(
      getSignalLabel({ indicator: "breakout", signal_type: "buy", lookback_period: 20 }, "entry")
    ).toBe("20일 고점 돌파");
    expect(
      getSignalLabel({ indicator: "breakout", signal_type: "sell", lookback_period: 20 }, "exit")
    ).toBe("20일 저점 이탈");
    // 기간 미상이면 일반 라벨을 유지한다.
    expect(getSignalLabel({ indicator: "breakout", signal_type: "buy" }, "entry")).toBe(
      "브레이크아웃"
    );
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

  // 시총 필터 값의 정본 단위는 **억원**이다(indicator_registry market_cap "억원",
  // 엔진 data_resolver `(close × shares) / 1e8`). 원 단위로 오해해 변환하던 탓에
  // '3000억 원 이상 3조 원 이하'가 요약 카드에 "시총 >= 3000 · 시총 <= 30000"으로
  // 단위 없이 보였다(2026-08-01 사용자 지적).
  it("시총 배지는 억원 단위 숫자를 한글 단위(억/조)로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 100 }))
      .toBe("시총 >= 100억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: ">=", value: 3000 }))
      .toBe("시총 >= 3,000억");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: "<=", value: 30000 }))
      .toBe("시총 <= 3조");
    expect(formatFundamentalFilter({ metric: "market_cap", operator: "<=", value: 15000 }))
      .toBe("시총 <= 1조 5,000억");
  });

  // 당기순이익(net_income)도 억원 단위 금액 필터다(2026-08-03 신설 — 시총과 같은 계약).
  it("당기순이익 배지는 억원 단위 숫자를 한글 단위(억/조)로 표시한다", () => {
    expect(formatFundamentalFilter({ metric: "net_income", operator: ">=", value: 1000 }))
      .toBe("당기순이익 >= 1,000억");
    expect(formatFundamentalFilter({ metric: "net_income", operator: ">=", value: 20000 }))
      .toBe("당기순이익 >= 2조");
  });

  // '최근 10년간'처럼 버킷 밖 기간은 명시 날짜로 변환돼 저장된다 — 창만 보여주면
  // 사용자가 말한 기간이 반영됐는지 알 수 없다(2026-08-02 지적).
  it("창의 길이가 딱 떨어지면 그 길이를 앞세운다", () => {
    expect(explicitWindowSpanLabel("2016-08-01", "2026-08-01")).toBe("10년");
    expect(explicitWindowSpanLabel("2025-02-02", "2026-08-02")).toBe("18개월");
    expect(formatBacktestPeriodLabel({
      backtest_period: "5y",
      backtest_start_date: "2016-08-01",
      backtest_end_date: "2026-08-01",
    })).toBe("10년 (2016-08-01 ~ 2026-08-01)");
  });

  it("딱 떨어지지 않는 창은 원래의 창 표기를 그대로 쓴다", () => {
    // 직접 지정한 연도 범위("2002년부터 2005년까지")를 길이로 뭉개지 않는다.
    expect(explicitWindowSpanLabel("2002-01-01", "2005-12-31")).toBeNull();
    expect(formatBacktestPeriodLabel({
      backtest_start_date: "2002-01-01",
      backtest_end_date: "2005-12-31",
    })).toBe("2002-01-01 ~ 2005-12-31");
    // 종료일이 없는 창(신규 상장 코호트)도 그대로다.
    expect(explicitWindowSpanLabel("2026-01-01", null)).toBeNull();
  });

  // 손절·익절·보유 기간을 '리스크'·'포트폴리오' 행으로 따로 보여주는 화면에서는
  // 청산 신호에 같은 값을 또 싣지 않는다 — 한 카드에서 같은 설정이 두 번 읽힌다
  // (2026-08-02 지시). 요약 카드와 진행 상황 카드가 이 술어 하나를 공유한다.
  it("청산 신호 라벨은 지표 신호만 싣는다", () => {
    const parsed = {
      ...baseParsed,
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 8,
      take_profit_pct: 30,
      trailing_stop_pct: 10,
      hold_period_days: 25,
    } as ParsedSummary;
    expect(getSignalExitLabels(parsed)).toEqual(["MA 데드크로스"]);
    // 같은 전략에 대해 결과 화면용 라벨은 위험 청산까지 싣는다(진입/청산 두 칸뿐).
    expect(getDisplayExitLabels(parsed).length).toBeGreaterThan(1);
  });

  it("지표 청산이 없으면 청산 신호 라벨은 비어 있다", () => {
    // 손절만 있는 전략은 '리스크' 행이 그 값을 보여주므로 청산 신호 행은 생략된다.
    const parsed = { ...baseParsed, exit_signals: [], stop_loss_pct: 8 } as ParsedSummary;
    expect(getSignalExitLabels(parsed)).toEqual([]);
    expect(getSignalExitLabels(null)).toEqual([]);
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
    expect(summary?.riskText).toBe("손절 -7%, 익절 10%");
  });

  it("손절 값이 이미 음수로 들어와도 부호를 중복해서 붙이지 않는다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      stop_loss_pct: -7,
    });

    expect(summary?.exitBlocks).toContain("손절 -7% 하락시 매도");
    expect(summary?.riskText).toBe("손절 -7%");
  });

  it("트레일링 스탑도 하락 방향이라 riskText에 마이너스로 표기한다", () => {
    const summary = buildStrategySummary({
      ...baseParsed,
      trailing_stop_pct: 10,
    });

    expect(summary?.exitBlocks).toContain("트레일링 스탑 -10% 하락시 매도");
    expect(summary?.riskText).toBe("트레일링 스탑 -10%");
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

  it("재무 팩터 랭킹 전략은 지표 라벨과 방향을 진입 신호 배지로 노출한다", () => {
    // 2026-08-03 신설 — '영업이익률 상위 20종목'류 재무 랭킹(모멘텀과 같은 선정=진입 계약).
    const top = buildStrategySummary({
      ...baseParsed,
      ranking_metric: "operating_margin",
    });
    expect(top?.entryBlocks).toEqual(["영업이익률 상위"]);

    const bottom = buildStrategySummary({
      ...baseParsed,
      ranking_metric: "per",
      ranking_direction: "bottom",
    });
    expect(bottom?.entryBlocks).toEqual(["PER 낮은 순 상위"]);
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
    expect(summary?.riskText).toBe("손절 -12%, 익절 10%");
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
    expect(summary?.riskText).toBe("손절 -12%");
  });

  it("심볼 CSV는 운용 전략 유니버스 배지로 표시하지 않는다", () => {
    const chips = buildStrategySummaryChips({
      universeName: "000020,000040,000050",
      entryBlocks: ["PBR <= 1"],
      exitBlocks: ["손절 -12% 하락시 매도"],
      positionText: "최대 8종목 · 126일 보유",
      riskText: "손절 -12%",
    });

    expect(chips).not.toContain("유니버스 000020,000040,000050");
    expect(chips).toEqual([
      "PBR <= 1",
      "손절 -12% 하락시 매도",
      "최대 8종목 · 126일 보유",
      "리스크 관리 손절 -12%",
    ]);
  });

  it("buildStrategySummaryGroups는 유니버스/진입신호/청산신호/리스트/리스크 관리로 묶어서 반환한다", () => {
    const groups = buildStrategySummaryGroups({
      universeName: "KOSPI · 반도체 업종",
      entryBlocks: ["126일 수익률 상위"],
      exitBlocks: ["손절 -10% 하락시 매도", "익절 20% 이상 수익시 매도"],
      positionText: "최대 5종목",
      riskText: "손절 -10%, 익절 20%",
    });

    expect(groups).toEqual([
      { label: "유니버스", chips: ["KOSPI · 반도체 업종"] },
      { label: "진입신호", chips: ["126일 수익률 상위"] },
      { label: "청산신호", chips: ["손절 -10% 하락시 매도", "익절 20% 이상 수익시 매도"] },
      { label: "리스트", chips: ["최대 5종목"] },
      { label: "리스크 관리", chips: ["손절 -10%, 익절 20%"] },
    ]);
  });

  it("buildStrategySummaryGroups는 비어있는 카테고리를 생략하고, 심볼 CSV 유니버스는 제외한다", () => {
    const groups = buildStrategySummaryGroups({
      universeName: "000020,000040,000050",
      entryBlocks: ["PBR <= 1"],
      exitBlocks: [],
      positionText: undefined,
      riskText: undefined,
    });

    expect(groups).toEqual([{ label: "진입신호", chips: ["PBR <= 1"] }]);
  });

  it("buildStrategySummaryGroups는 null/undefined 입력에 빈 배열을 반환한다", () => {
    expect(buildStrategySummaryGroups(null)).toEqual([]);
    expect(buildStrategySummaryGroups(undefined)).toEqual([]);
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
    expect(summary?.riskText).toBe("손절 -10%, 익절 20%");
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

describe("섹터/업종 유니버스 표시", () => {
  it("parsed.sector가 있으면 유니버스 라벨에 업종 배지를 덧붙인다", () => {
    const labels = getDisplayUniverseLabels({
      ...baseParsed,
      universe: ["KOSPI", "KOSDAQ"],
      sector: "반도체",
    });
    expect(labels).toEqual(["KOSPI", "KOSDAQ", "반도체 업종"]);
  });

  it("sector가 없으면 기존 라벨 그대로다", () => {
    expect(getDisplayUniverseLabels(baseParsed)).toEqual(["KOSPI"]);
  });

  it("실행된 요청의 sector도 유니버스명에 반영한다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kosdaq_kospi",
      sector: "반도체",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: {},
    });
    expect(summary?.universeName).toContain("반도체 업종");
  });

  it("복수 섹터(배열)는 업종별 개별 배지를 만든다 (FR-STR-066 ⑦)", () => {
    // [회귀] "로봇 섹터도 추가해줘" — 다중 섹터가 배열로 오면 각 업종이 배지로 보여야 한다.
    const labels = getDisplayUniverseLabels({
      ...baseParsed,
      universe: ["KOSPI", "KOSDAQ"],
      sector: ["반도체", "기계/장비"],
    });
    expect(labels).toEqual(["KOSPI", "KOSDAQ", "반도체 업종", "기계/장비 업종"]);

    const summary = buildStrategySummaryFromRequest({
      universe_id: "kosdaq_kospi",
      sector: ["반도체", "기계/장비"],
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: {},
    });
    expect(summary?.universeName).toContain("반도체 업종");
    expect(summary?.universeName).toContain("기계/장비 업종");
  });
});

describe("ETF 유니버스 표시 (2026-07-19)", () => {
  it("universe ETF는 ETF 라벨로 표시된다", () => {
    const labels = getDisplayUniverseLabels({
      ...baseParsed,
      universe: ["ETF"],
    });
    expect(labels).toEqual(["ETF"]);
  });

  it("etf_theme 키워드는 테마 배지, 상품명은 그대로 배지가 된다", () => {
    expect(
      getDisplayUniverseLabels({
        ...baseParsed,
        universe: ["ETF"],
        etf_theme: "반도체",
      })
    ).toEqual(["ETF", "반도체 테마"]);

    expect(
      getDisplayUniverseLabels({
        ...baseParsed,
        universe: ["ETF"],
        etf_theme: "KODEX 200",
      })
    ).toEqual(["ETF", "KODEX 200"]);
  });
});

describe("단일/지정 종목 백테스트 표시 (FR-STR-068)", () => {
  it("지정 종목이 있으면 유니버스 대신 종목명 배지를 만든다", () => {
    expect(
      getDisplayUniverseLabels(
        { ...baseParsed, target_symbols: ["005930"] },
        { target_stocks: [{ symbol: "005930", name: "삼성전자" }] }
      )
    ).toEqual(["삼성전자 (005930)"]);
  });

  it("이름 메타데이터가 없으면 종목코드만 표시한다", () => {
    expect(
      getDisplayUniverseLabels({ ...baseParsed, target_symbols: ["005930"] }, null)
    ).toEqual(["005930"]);
  });

  it("지정 종목이 없으면 기존 유니버스 라벨을 유지한다", () => {
    expect(getDisplayUniverseLabels(baseParsed, null)).toEqual(["KOSPI"]);
  });

  it("buildStrategySummary가 단일 종목 집중 투자를 표기한다", () => {
    const summary = buildStrategySummary(
      { ...baseParsed, target_symbols: ["005930"] },
      { target_stocks: [{ symbol: "005930", name: "삼성전자" }] }
    );
    expect(summary?.universeName).toBe("삼성전자 (005930)");
    expect(summary?.positionText).toContain("단일 종목");
  });

  it("실행된 요청(target_stocks)에서도 종목 배지·집중 투자 문구를 만든다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: null,
      target_stocks: [{ symbol: "005930", name: "삼성전자" }],
      entry: { conditions: [{ id: "ma_crossover", type: "indicator" }] },
      exit: { conditions: [] },
      risk: { max_positions: 1, position_size_pct: 100 },
    });
    expect(summary?.universeName).toBe("삼성전자 (005930)");
    expect(summary?.positionText).toBe("단일 종목 집중 투자");
  });

  it("저장 DSL(target_symbols)에서도 종목 배지·집중 투자 문구를 만든다", () => {
    const summary = buildStrategySummaryFromDsl({
      description: "삼성전자 골든크로스",
      target_symbols: ["005930"],
      risk: { max_positions: 1 },
    } as never);
    expect(summary?.universeName).toBe("005930");
    expect(summary?.positionText).toContain("단일 종목");
  });
});

describe("신규 상장 유니버스 표시 (FR-STR-073)", () => {
  it("상장 구간이 한 해 전체면 연도 배지를 만든다", () => {
    expect(
      getDisplayUniverseLabels({
        ...baseParsed,
        universe: ["KOSPI", "KOSDAQ"],
        new_listing_only: true,
        listing_from: "2026-01-01",
        listing_to: "2026-12-31",
      })
    ).toEqual(["KOSPI", "KOSDAQ", "2026년 상장"]);
  });

  it("상한이 없으면 '이후 상장'으로 표기한다", () => {
    expect(
      getDisplayUniverseLabels({
        ...baseParsed,
        universe: ["KOSDAQ"],
        new_listing_only: true,
        listing_from: "2025-06-01",
      })
    ).toEqual(["KOSDAQ", "2025-06-01 이후 상장"]);
  });

  it("대상 시기를 되묻는 중이면 개념만 배지로 남는다", () => {
    // 구간이 없다고 배지를 지우면 사용자가 말한 제한이 화면에서 사라진다.
    expect(
      getDisplayUniverseLabels({
        ...baseParsed,
        universe: ["KOSPI", "KOSDAQ"],
        new_listing_only: true,
      })
    ).toEqual(["KOSPI", "KOSDAQ", "신규 상장"]);
  });

  it("제한이 없으면 배지를 만들지 않는다", () => {
    expect(formatNewListingLabel(baseParsed)).toBeNull();
    expect(getDisplayUniverseLabels(baseParsed)).toEqual(["KOSPI"]);
  });

  it("실행된 요청의 상장 구간도 유니버스명에 반영한다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kosdaq_kospi",
      listing_from: "2026-01-01",
      listing_to: "2026-12-31",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: {},
    });
    expect(summary?.universeName).toContain("2026년 상장");
  });
});
