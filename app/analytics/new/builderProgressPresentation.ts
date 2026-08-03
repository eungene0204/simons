import {
  formatFundamentalFilter,
  formatInitialCapital,
  formatDownsidePercent,
  getDisplayUniverseLabels,
  getPositionLabel,
  getRankingLabel,
  getSignalExitLabels,
  getSignalLabel,
  formatBacktestPeriodLabel,
  formatNewListingLabel,
  type ParsedSummary,
} from "./strategySummary";
import { isExplicit, isSlotFilled } from "./backtestReadiness";

export type BuilderSummaryItem = {
  label: string;
  value: string;
};

// 진행 골격 8칸의 두 상태 축(백엔드 engine/strategy_slots.py와 동일).
// complete(불리언)가 뭉개던 것을 나눈다 — 특히 '해당 없음'과 '완료'의 구분.
//
// 두 축을 분리해 두는 이유: 값 축은 사용자 소유의 **영속** 상태이고, 파생 축은
// 현재 전략 전체를 기준으로 백엔드가 **매 턴 다시 계산**하는 값이다. 하나로 합치면
// "값은 확정인데 지금 유니버스에서 못 쓴다"가 표현되지 않는다.
export type ValueStatus = "UNKNOWN" | "INFERRED" | "PROVISIONAL" | "CONFIRMED";
export type DerivedStatus =
  | "APPLICABLE"
  | "NOT_APPLICABLE"
  | "INVALID"
  | "CONFLICTED";

/** 백엔드 field_states 페이로드의 슬롯 하나. */
export type SlotState = { value?: ValueStatus; derived?: DerivedStatus };

export type BuilderProgressItem = {
  label: string;
  complete: boolean;
  // 백엔드가 계산한 상태(없으면 기존 complete 표시 그대로). 판정은 백엔드 SOT가
  // 소유하며 프론트는 표시만 한다 — 같은 판정의 두 번째 구현을 만들지 않는다.
  valueStatus?: ValueStatus;
  derivedStatus?: DerivedStatus;
};

/** 두 축을 화면 문구 하나로 줄인다(표시 전용 — 판정이 아니다).
 *  파생 축이 먼저다: 지금 못 쓰는 칸은 값이 확정이어도 손이 필요하다. */
export function progressStatusText(item: BuilderProgressItem): string | undefined {
  if (item.derivedStatus === "NOT_APPLICABLE") return "해당 없음";
  if (item.derivedStatus === "INVALID" || item.derivedStatus === "CONFLICTED") {
    return "확인 필요";
  }
  if (item.valueStatus === "PROVISIONAL") return "미확인";
  return undefined;
}

// 진행률 카드가 슬롯 이름을 상황에 따라 바꿔 다는 자리 — 백엔드 슬롯 어휘로 되돌린다.
const PROGRESS_LABEL_TO_SLOT: Record<string, string> = {
  포트폴리오: "최대 보유",
  "투자 대상": "유니버스",
};

/** 진행률 분자·분모. '해당 없음'은 물을 대상이 아니므로 양쪽 모두에서 뺀다 —
 * 완료로 세면 진행률이 실제보다 높게 보이고, 미완료로 세면 영원히 채울 수 없다. */
export function countProgress(
  items: BuilderProgressItem[],
): { completed: number; total: number } {
  const applicable = items.filter((item) => item.derivedStatus !== "NOT_APPLICABLE");
  return {
    completed: applicable.filter((item) => item.complete).length,
    total: applicable.length,
  };
}

/** 백엔드 상태 맵을 진행률 항목에 붙인다. 없는 항목은 상태 없이 남는다. */
export function attachFieldStates(
  items: BuilderProgressItem[],
  fieldStates: Record<string, SlotState> | null | undefined,
): BuilderProgressItem[] {
  if (!fieldStates) return items;
  return items.map((item) => {
    const slot = PROGRESS_LABEL_TO_SLOT[item.label] ?? item.label;
    const state = fieldStates[slot];
    if (!state) return item;
    return {
      ...item,
      ...(state.value ? { valueStatus: state.value } : {}),
      ...(state.derived ? { derivedStatus: state.derived } : {}),
    };
  });
}

export type BuilderTurnPresentation = {
  summaryItems: BuilderSummaryItem[];
  progressItems: BuilderProgressItem[];
  question: string;
};

/** 백엔드 pending_conditions 페이로드 항목 — 값 미정으로 컴파일에서 제외된 조건.
 *  parsed에는 없다(말하지 않은 값을 기본값으로 확정하지 않는 계약). 이 채널이 요약에
 *  반영되지 않으면 이해한 조건이 빈 전략으로 보인다(2026-08-03 '당기순이익' 사고). */
export type PendingCondition = {
  role: "entry" | "exit";
  label: string;
  source_text?: string | null;
};

/** 값-대기 조건의 요약 표기. 사용자가 말한 표현(source_text)이 정본 라벨과 다른
 *  지표로 매핑됐으면(예: '당기순이익' → 순이익증가율) 치환을 함께 고지한다 —
 *  비교 입력은 둘 다 LLM 구조화 출력이다(원문 재해석 아님). */
function formatPendingCondition(p: PendingCondition): string {
  const base = `${p.label}(값 미정)`;
  const source = (p.source_text ?? "").trim();
  if (!source) return base;
  const normalize = (s: string) => s.replace(/\s+/g, "").toLowerCase();
  // 라벨의 괄호 병기("PER(주가수익비율)")는 비교에서 뗀다 — 원문에는 약칭만 온다.
  const labelKey = normalize(p.label.replace(/\(.*\)$/, ""));
  if (normalize(source).includes(labelKey)) return base;
  return `'${source}' → ${base}`;
}

export function getDisplayBuilderProgressItems(
  items: BuilderProgressItem[],
): BuilderProgressItem[] {
  const normalizedItems = items.map((item) => ({
    ...item,
    label: item.label === "투자 대상" ? "유니버스" : item.label,
  }));

  return [
    ...normalizedItems.filter((item) => item.complete),
    ...normalizedItems.filter((item) => !item.complete),
  ];
}

const UNIVERSE_LABELS: Record<string, string> = {
  KOSPI: "KOSPI",
  KOSDAQ: "KOSDAQ",
  KOSPI200: "KOSPI 200",
  KOSPI_KOSDAQ: "KOSPI·KOSDAQ 전체",
  ETF: "ETF",
};

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "모멘텀",
  golden_cross: "골든크로스",
  macd: "MACD",
  bollinger: "볼린저 밴드",
  breakout: "돌파",
  volume_spike: "거래량 급증",
  stochastic: "스토캐스틱",
  cci: "CCI",
  rsi: "RSI",
  mean_reversion: "과매도 반등",
  value: "저평가 가치주",
  custom: "직접 설계",
};

const REBALANCE_LABELS: Record<string, string> = {
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  quarterly: "분기",
  yearly: "매년",
  none: "설정 안 함",
};

const PAIRED_EXIT_STRATEGIES = new Set([
  "golden_cross",
  "macd",
  "bollinger",
  "stochastic",
  "cci",
  "rsi",
  "mean_reversion",
]);

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "" && value !== false;
}

function isEntryComplete(state: Record<string, any>, parsed?: ParsedSummary | null): boolean {
  const parsedHasEntry = Boolean(
    parsed?.fundamental_filters?.length ||
    parsed?.entry_signals?.length ||
    parsed?.ranking_metric,
  );
  if (parsedHasEntry) return true;

  const strategyType = state.strategy_type;
  if (!strategyType) return false;
  if (strategyType === "custom") return hasValue(state.entry_rule);
  if (strategyType === "momentum" || strategyType === "breakout") {
    return hasValue(state.lookback_days);
  }
  if (strategyType === "rsi") {
    return hasValue(state.rsi_period) &&
      hasValue(state.rsi_oversold) &&
      hasValue(state.rsi_overbought) &&
      state.filters_asked === true;
  }
  if (strategyType === "golden_cross") {
    return hasValue(state.ma_kind) &&
      hasValue(state.ma_short) &&
      hasValue(state.ma_long) &&
      state.filters_asked === true;
  }
  if (strategyType === "macd") {
    return hasValue(state.macd_mode) && state.filters_asked === true;
  }
  if (strategyType === "cci") {
    return hasValue(state.cci_period) &&
      hasValue(state.cci_threshold) &&
      state.filters_asked === true;
  }
  if (strategyType === "volume_spike") {
    return hasValue(state.volume_period) && state.filters_asked === true;
  }
  if (strategyType === "value") {
    return hasValue(state.value_pbr) && hasValue(state.value_roe);
  }
  return state.filters_asked === true;
}

function buildEntryLabel(
  state: Record<string, any>,
  parsed?: ParsedSummary | null,
): string | null {
  const parsedLabels = [
    ...(parsed?.fundamental_filters ?? []).map(formatFundamentalFilter),
    ...(parsed?.entry_signals ?? []).map((signal) => getSignalLabel(signal, "entry")),
    ...(parsed && getRankingLabel(parsed) ? [getRankingLabel(parsed)!] : []),
  ];
  if (parsedLabels.length > 0) return parsedLabels.join(" · ");

  if (state.entry_rule) return String(state.entry_rule);
  const strategyLabel = STRATEGY_LABELS[state.strategy_type];
  return strategyLabel ? `${strategyLabel} 조건` : null;
}

function buildRiskLabel(state: Record<string, any>, parsed?: ParsedSummary | null): string | null {
  const labels: string[] = [];
  const stopLoss = state.stop_loss_pct ?? parsed?.stop_loss_pct;
  const takeProfit = state.take_profit_pct ?? parsed?.take_profit_pct;
  const trailingStop = state.trailing_stop_pct ?? parsed?.trailing_stop_pct;
  const holdPeriod = state.hold_period_days ?? parsed?.hold_period_days;
  if (hasValue(stopLoss)) labels.push(`손절 ${formatDownsidePercent(stopLoss)}%`);
  if (hasValue(takeProfit)) labels.push(`익절 ${takeProfit}%`);
  if (hasValue(trailingStop)) labels.push(`트레일링 스탑 ${formatDownsidePercent(trailingStop)}%`);
  if (hasValue(holdPeriod)) labels.push(`${holdPeriod}일 보유`);
  return labels.length > 0 ? labels.join(" · ") : null;
}

export function makeBuilderQuestionFriendly(reply: string): string {
  return reply
    .replace(
      "대상 시장·종목이 빠져 있습니다. 어떤 시장·종목을 대상으로 할까요?",
      "먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?",
    )
    .replace(
      "매수 조건이 빠져 있습니다. 어떤 조건에서 매수할까요?",
      "다음으로 어떤 조건에서 매수할지 정해볼까요?",
    )
    .replace(
      "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
      "이제 언제 매도할지 정해볼까요?",
    )
    .replace(
      "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      "다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?",
    )
    .replace(
      "손절 기준이 빠져 있습니다. 손절 기준을 몇 %로 설정할까요?",
      "이제 손절 기준을 몇 %로 정할까요?",
    )
    .replace(
      "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      "이제 익절 기준을 몇 %로 정할까요?",
    )
    .replace(/^세부 조건이 빠져 있습니다\.\s*/, "")
    .replace(/^[^.\n]+(?:빠져 있습니다|빠졌습니다)\.\s*/, "")
    .replace("과매도·과매수 기준을 정해 주세요.", "과매도·과매수 기준을 정해볼까요?")
    .replace("단기·장기 이동평균 기간을 정해 주세요.", "단기·장기 이동평균 기간을 정해볼까요?")
    .replace("CCI 기준값을 정해 주세요.", "CCI 기준값을 정해볼까요?")
    .replace("저평가 기준을 정해 주세요.", "저평가 기준을 정해볼까요?")
    .replace(
      "어떤 조건에서 매수할지 말씀해 주세요.",
      "어떤 조건에서 매수할지 함께 정해볼까요?",
    )
    .replace(
      /마지막으로 청산 조건을 정해 주세요\. 손절·익절·트레일링 스탑·보유기간 중 하나 이상을 자유롭게 말씀해 주세요\./,
      "이제 언제 매도할지 정하면 전략이 완성됩니다. 손절·익절·트레일링 스탑·보유기간 중 하나를 정해볼까요?",
    )
    .replace(
      "마지막으로 청산 조건을 정해 주세요.",
      "이제 언제 매도할지 정하면 전략이 완성됩니다. 매도 조건을 함께 정해볼까요?",
    );
}

export function buildBuilderTurnPresentation({
  state,
  reply,
  parsed,
  explicitFields,
  backtestRequest,
  allowNoRebalancing,
  pendingConditions,
}: {
  state: Record<string, any>;
  reply: string;
  parsed?: ParsedSummary | null;
  // 사용자가 실제로 말한 설정 필드(백엔드 provenance). 원문 정규식 재분석을 대체한다.
  explicitFields?: readonly string[];
  // 지정 종목 표시용 이름(backtest_request.target_stocks) — 없으면 코드만 표시된다.
  backtestRequest?: {
    symbols?: string[];
    target_stocks?: Array<{ symbol: string; name?: string }> | null;
  } | null;
  // 사용자가 리밸런싱 '안 함'을 고른 결과(게이트와 같은 입력). LLM 스펙에서는 null이라
  // 미언급과 구분되지 않으므로 호출자가 들고 전달한다 — 없으면 진행률이 그 답을 놓친다.
  allowNoRebalancing?: boolean;
  // 값 미정으로 컴파일에서 제외된 조건(백엔드 pending_conditions) — parsed에 없으므로
  // 여기서 받지 않으면 이해한 조건이 요약에서 사라진다.
  pendingConditions?: readonly PendingCondition[] | null;
}): BuilderTurnPresentation {
  const summaryItems: BuilderSummaryItem[] = [];
  // 신규 상장 제한(FR-STR-073)은 시장 라벨에 덧붙인다 — 빼면 "코스피·코스닥 전체"만
  // 보여 전 종목을 대상으로 하는 것처럼 읽힌다(2026-07-29 사고와 같은 오해).
  const newListingSuffix = formatNewListingLabel({
    new_listing_only: state.new_listing_only,
    listing_from: state.listing_from,
    listing_to: state.listing_to,
  });
  const marketFromState = state.universe
    ? UNIVERSE_LABELS[state.universe] ?? state.universe
    : null;
  const targetFromState = (state.single_label
    ? String(state.single_label).replace(/\s*\(\d{6}\)$/, "")
    : null) ||
    (state.theme_label ? String(state.theme_label) : null) ||
    (marketFromState
      ? [marketFromState, newListingSuffix].filter(Boolean).join(" · ")
      : null);
  // 빌더 레인의 state 값은 사용자가 되묻기에 직접 답한 결과다 — 그 자체가 명시다.
  // (백엔드 provenance는 자유 서술 파스 레인의 판정을 담당한다. 두 레인 모두 근거는
  //  사용자의 실제 발화이고, 어느 쪽도 원문 정규식을 쓰지 않는다.)
  const targetExplicit =
    Boolean(state.theme_label) ||
    Boolean(state.single_label) ||
    Boolean(state.universe) ||
    isExplicit("universe", explicitFields, parsed);
  const target = targetExplicit
    ? targetFromState ||
      (parsed ? getDisplayUniverseLabels(parsed, backtestRequest).join(" · ") : null)
    : null;
  const entryLabel = buildEntryLabel(state, parsed);
  // '매도 조건'은 지표가 만드는 청산 신호만 싣는다 — 손절·익절·트레일링·보유 기간은
  // 아래 '리스크 관리' 항목이 같은 값을 그대로 보여주므로, 함께 넣으면 한 카드에서
  // 같은 설정이 두 번 읽힌다(2026-08-02 지시 — 요약 카드와 같은 정리).
  const exitLabels = getSignalExitLabels(parsed);
  const riskLabel = buildRiskLabel(state, parsed);
  const specifiedSymbolCount = parsed?.target_symbols?.length ?? 0;
  const holdingCountFromState = hasValue(state.holding_count);
  const holdingCount = holdingCountFromState ? state.holding_count : parsed?.max_positions;
  const holdingCountExplicit =
    holdingCountFromState || isExplicit("max_positions", explicitFields);
  const rebalanceFromState = hasValue(state.rebalance_cycle);
  const rebalanceCycle = rebalanceFromState
    ? state.rebalance_cycle
    : parsed?.rebalancing_period;
  // 지정 종목 1개(단독 종목)만 리밸런싱을 확정 표시한다(교체가 없어 '설정 안 함'이 사실).
  // 다종목 지정(테마 유니버스 등)은 포트폴리오라 사용자가 답하기 전까지 기본값을 확정된
  // 것처럼 보여주지 않는다(2026-07-28 '모바일솔루션 관련주' 사고 — 질문 없이 '설정 안 함' 노출).
  const rebalanceExplicit =
    specifiedSymbolCount === 1 ||
    rebalanceFromState ||
    isExplicit("rebalancing", explicitFields);
  const backtestPeriod = state.backtest_period ?? state.period ?? parsed?.backtest_period;
  // 슬롯 판정은 게이트와 **같은 술어**(isSlotFilled)에 맡기고, 빌더 state로만 알 수 있는
  // 추가 근거(사용자가 되묻기에 직접 답한 값)를 OR로 얹는다. 판정을 여기 다시 적으면
  // 게이트만 고쳐지고 진행률은 낡은 채 남는다 — 2026-07-29 사고와 그때 함께 드러난
  // 기존 드리프트 3종(매도 조건·리스크 관리·리밸런싱 거부)이 전부 그 경로였다.
  const slotOptions = {
    explicitFields,
    requireExplicitConfiguration: true,
    // 빌더가 리밸런싱 '안 함'을 들고 있으면 사용자의 명시적 결정이다(게이트와 같은 계약).
    allowNoRebalancing: allowNoRebalancing === true || state.rebalance_cycle === "none",
  };
  const slotFilled = (field: Parameters<typeof isSlotFilled>[0]) =>
    isSlotFilled(field, parsed, slotOptions);
  const backtestPeriodSettled =
    hasValue(state.backtest_period ?? state.period) || slotFilled("backtest_period");
  const initialCapitalFromState = state.initial_capital ?? state.init_cash;
  const initialCapital = hasValue(initialCapitalFromState)
    ? Number(initialCapitalFromState)
    : parsed?.initial_capital;
  const initialCapitalExplicit =
    hasValue(initialCapitalFromState) || isExplicit("initial_capital", explicitFields);

  if (target) {
    summaryItems.push({
      label: state.single_label || state.theme_label ? "대상 종목" : "유니버스",
      value: target,
    });
  }
  if (state.sector || parsed?.sector) {
    const sector = state.sector ?? parsed?.sector;
    summaryItems.push({
      label: "업종",
      value: Array.isArray(sector) ? sector.join(" · ") : String(sector),
    });
  }
  // 값-대기 조건은 확정 조건 뒤에 덧붙인다 — 확정/미정을 한 행에서 함께 보여야
  // "이해했지만 값을 기다린다"가 전달된다(빈 요약 = '이해 못함' 오독 방지).
  const pendingEntry = (pendingConditions ?? [])
    .filter((p) => p.role === "entry")
    .map(formatPendingCondition);
  const pendingExit = (pendingConditions ?? [])
    .filter((p) => p.role === "exit")
    .map(formatPendingCondition);
  const entryValue = [...(entryLabel ? [entryLabel] : []), ...pendingEntry].join(" · ");
  if (entryValue) summaryItems.push({ label: "매수 조건", value: entryValue });
  const exitValue = [...exitLabels, ...pendingExit].join(" · ");
  if (exitValue) summaryItems.push({ label: "매도 조건", value: exitValue });
  if (parsed && specifiedSymbolCount > 0) {
    // 지정 종목 모드의 배분은 max_positions가 아니라 종목 수 균등이다 — 변환기가
    // max_positions=지정 종목 수로 덮어쓴다(FR-STR-068 ①, ranking_enabled=off). 기본값
    // '최대 보유 10종목'을 실행값처럼 보여주지 않고(2026-07-28 '모바일솔루션 관련주'
    // 카드-실행 불일치) 실제 배분 표기(FR-STR-068 ⑧)를 쓴다 — 파싱 카드와 동일.
    summaryItems.push({ label: "포트폴리오", value: getPositionLabel(parsed) });
  } else if (holdingCount && holdingCountExplicit) {
    summaryItems.push({
      label: "최대 보유",
      value: `${holdingCount}종목`,
    });
  }
  if (rebalanceCycle && rebalanceExplicit) {
    const normalizedCycle = String(rebalanceCycle);
    const cycle = REBALANCE_LABELS[normalizedCycle] ?? normalizedCycle;
    summaryItems.push({
      label: "리밸런싱",
      value: cycle,
    });
  }
  // 명시 날짜가 있으면 상대 기간 라벨("5년") 대신 실제 창을 보여준다 — 신규 상장
  // 코호트처럼 시스템이 창을 조정한 경우 라벨과 실행 구간이 어긋난다(FR-STR-073).
  const periodLabel = formatBacktestPeriodLabel({
    backtest_period: backtestPeriod,
    backtest_start_date: parsed?.backtest_start_date,
    backtest_end_date: parsed?.backtest_end_date,
  });
  if (periodLabel && backtestPeriodSettled) {
    summaryItems.push({ label: "백테스트 기간", value: periodLabel });
  }
  if (initialCapital && initialCapitalExplicit) {
    summaryItems.push({
      label: "초기 자본",
      value: formatInitialCapital(initialCapital),
    });
  }
  if (riskLabel) summaryItems.push({ label: "리스크 관리", value: riskLabel });

  const entryComplete = isEntryComplete(state, parsed);
  // 리스크 관리 슬롯은 손절·익절이 **둘 다** 있어야 완료다(정본 계약) — 배지가 하나라도
  // 있으면 완료로 보던 드리프트를 제거했다. 빌더가 청산 단계를 마쳤으면(risk_done)
  // 사용자가 답을 끝낸 것이므로 그것도 완료 근거다.
  const riskComplete =
    state.risk_done === true || (slotFilled("stop_loss") && slotFilled("take_profit"));
  // 매도 조건은 청산 신호·보유기간·정기 리밸런싱이다 — 손절·익절은 '리스크 관리' 슬롯이라
  // 여기서 인정하지 않는다(체크는 켜지고 시스템은 청산을 되묻던 어긋남).
  const exitComplete =
    slotFilled("exit") || (entryComplete && PAIRED_EXIT_STRATEGIES.has(state.strategy_type));

  return {
    summaryItems,
    progressItems: [
      { label: "유니버스", complete: Boolean(target) && targetExplicit },
      { label: "매수 조건", complete: entryComplete },
      { label: "매도 조건", complete: exitComplete },
      {
        label: specifiedSymbolCount > 0 ? "포트폴리오" : "최대 보유",
        complete:
          specifiedSymbolCount > 0 || (Boolean(holdingCount) && holdingCountExplicit),
      },
      { label: "리밸런싱", complete: (Boolean(rebalanceCycle) && rebalanceExplicit) || slotFilled("rebalancing") },
      { label: "리스크 관리", complete: riskComplete },
      // 게이트와 **같은 술어**를 쓴다 — 판정을 여기 다시 적으면 게이트만 고쳐지고 진행률은
      // 낡은 채 남는다(2026-07-29: 창이 자동 확정됐는데 체크가 안 되던 사고).
      { label: "백테스트 기간", complete: backtestPeriodSettled },
      { label: "초기 자본", complete: Boolean(initialCapital) && initialCapitalExplicit },
    ],
    question: makeBuilderQuestionFriendly(reply),
  };
}
