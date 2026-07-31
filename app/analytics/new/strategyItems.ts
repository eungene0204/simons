/** 전략에 지금 설정돼 있는 항목들 — "무엇을 그대로 두고 무엇을 바꿀지" 고르게 하는 목록.
 *
 * 목록은 **상태에서 결정론으로** 만든다. 인터프리터가 낸 확인 질문 문장을 파싱해 만들면
 * LLM이 쓴 자유 텍스트를 정규식으로 해석하는 구조가 되고(대원칙 1 위반), 각 줄이 어느
 * 필드인지도 LLM 판단에 의존하게 된다. 여기서는 값이 곧 항목이라 결속이 공짜로 성립하며,
 * 진행률 패널도 같은 슬롯 술어(isSlotFilled)를 보므로 싱크가 자동으로 맞는다.
 *
 * 라벨은 요약 카드가 쓰는 포매터를 그대로 재사용한다 — 같은 값이 화면 두 곳에서 다르게
 * 보이지 않게 한다.
 */
import {
  formatBacktestPeriodLabel,
  formatFundamentalFilter,
  getDisplayUniverseLabels,
  getSignalLabel,
} from "@/lib/strategy-summary";

import type { MissingBacktestCondition } from "./backtestReadiness";
import type { ParsedSummary } from "./strategySummary";

export type StrategyItemSlot = MissingBacktestCondition["field"];

export type StrategyItem = {
  /** 안정 식별자 — 체크 상태와 지우기 대상을 가리킨다. */
  id: string;
  /** 진행 골격 슬롯(진행률 패널과 같은 축). */
  slot: StrategyItemSlot;
  /** 항목 종류 라벨("매수 조건"). */
  label: string;
  /** 현재 값 표기("ROE 10% 이상"). */
  value: string;
};

const REBALANCE_LABELS: Record<string, string> = {
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  bimonthly: "격월",
  quarterly: "분기",
  yearly: "매년",
  none: "리밸런싱 안 함",
};

function formatCapital(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toLocaleString()}억원`;
  if (value >= 10_000) return `${(value / 10_000).toLocaleString()}만원`;
  return `${value.toLocaleString()}원`;
}

/** 지금 설정돼 있는 항목을 진행 골격 순서로 나열한다(값이 없는 항목은 나오지 않는다). */
export function listStrategyItems(parsed: ParsedSummary | null | undefined): StrategyItem[] {
  if (!parsed) return [];
  const items: StrategyItem[] = [];

  const universeLabels = getDisplayUniverseLabels(parsed);
  if (universeLabels.length > 0) {
    items.push({
      id: "universe",
      slot: "universe",
      label: "유니버스",
      value: universeLabels.join(" · "),
    });
  }

  (parsed.fundamental_filters ?? []).forEach((filter, i) => {
    items.push({
      id: `fundamental.${i}`,
      slot: "entry",
      label: "매수 조건",
      value: formatFundamentalFilter(filter),
    });
  });
  (parsed.entry_signals ?? []).forEach((signal, i) => {
    items.push({
      id: `entry.${i}`,
      slot: "entry",
      label: "매수 조건",
      value: getSignalLabel(signal, "entry"),
    });
  });
  (parsed.exit_signals ?? []).forEach((signal, i) => {
    items.push({
      id: `exit.${i}`,
      slot: "exit",
      label: "매도 조건",
      value: getSignalLabel(signal, "exit"),
    });
  });

  if ((parsed.max_positions ?? 0) > 0) {
    items.push({
      id: "max_positions",
      slot: "max_positions",
      label: "최대 보유",
      value: `${parsed.max_positions}종목`,
    });
  }
  if (parsed.rebalancing_period) {
    items.push({
      id: "rebalancing",
      slot: "rebalancing",
      label: "리밸런싱",
      value: REBALANCE_LABELS[String(parsed.rebalancing_period)] ?? String(parsed.rebalancing_period),
    });
  }
  if ((parsed.hold_period_days ?? 0) > 0) {
    items.push({
      id: "hold_period",
      slot: "exit",
      label: "보유 기간",
      value: `최대 ${parsed.hold_period_days}일 보유`,
    });
  }
  if ((parsed.stop_loss_pct ?? 0) > 0) {
    items.push({
      id: "stop_loss",
      slot: "stop_loss",
      label: "손절",
      value: `-${parsed.stop_loss_pct}%`,
    });
  }
  if ((parsed.take_profit_pct ?? 0) > 0) {
    items.push({
      id: "take_profit",
      slot: "take_profit",
      label: "익절",
      value: `+${parsed.take_profit_pct}%`,
    });
  }
  if ((parsed.trailing_stop_pct ?? 0) > 0) {
    items.push({
      id: "trailing_stop",
      slot: "stop_loss",
      label: "트레일링 스탑",
      value: `-${parsed.trailing_stop_pct}%`,
    });
  }

  const periodLabel = formatBacktestPeriodLabel(parsed);
  if (periodLabel) {
    items.push({
      id: "backtest_period",
      slot: "backtest_period",
      label: "백테스트 기간",
      value: periodLabel,
    });
  }
  if ((parsed.initial_capital ?? 0) > 0) {
    items.push({
      id: "initial_capital",
      slot: "initial_capital",
      label: "초기 자본",
      value: formatCapital(parsed.initial_capital as number),
    });
  }
  return items;
}

/** 고른 항목들을 전략에서 **비운다**(원본 불변).
 *
 *  비우는 방식이 두 가지인 이유는 슬롯 판정(isSlotFilled)이 그렇게 생겼기 때문이다:
 *   · 값의 존재가 곧 완료인 항목(진입·청산 신호·손절·익절·보유기간) → **값을 지운다**
 *   · 기본값이 물질화되는 설정(유니버스·종목 수·리밸런싱·기간·초기 자본) → 값이 아니라
 *     **"사용자가 말했다"는 기록(explicit_fields)을 지운다**. 값을 0/""로 만들면 백엔드
 *     스키마와 싸우게 되고, 애초에 이 슬롯들의 완료 조건이 provenance다.
 *  어느 쪽이든 진행률 언체크는 같은 술어로 자동 성립한다 — 새 상태 축을 만들지 않는다.
 */
export type ClearedStrategy = {
  parsed: ParsedSummary;
  /** explicit_fields에서 빼야 하는 필드(기본값 물질화 슬롯). */
  dropExplicitFields: string[];
};

const EXPLICIT_FIELD_BY_ID: Record<string, string> = {
  universe: "universe",
  max_positions: "max_positions",
  rebalancing: "rebalancing",
  backtest_period: "backtest_period",
  initial_capital: "initial_capital",
};

export function clearStrategyItems(
  parsed: ParsedSummary,
  ids: readonly string[],
): ClearedStrategy {
  const drop = new Set(ids);
  const next: ParsedSummary = { ...parsed };

  const dropIndexed = (prefix: string, list: unknown[] | undefined) =>
    (list ?? []).filter((_, i) => !drop.has(`${prefix}.${i}`));

  next.fundamental_filters = dropIndexed("fundamental", parsed.fundamental_filters) as
    ParsedSummary["fundamental_filters"];
  next.entry_signals = dropIndexed("entry", parsed.entry_signals) as
    ParsedSummary["entry_signals"];
  next.exit_signals = dropIndexed("exit", parsed.exit_signals) as
    ParsedSummary["exit_signals"];

  if (drop.has("hold_period")) next.hold_period_days = null;
  if (drop.has("stop_loss")) next.stop_loss_pct = null;
  if (drop.has("take_profit")) next.take_profit_pct = null;
  if (drop.has("trailing_stop")) next.trailing_stop_pct = null;

  const dropExplicitFields = [...drop]
    .map((id) => EXPLICIT_FIELD_BY_ID[id])
    .filter((field): field is string => Boolean(field));
  return { parsed: next, dropExplicitFields };
}

/** 비운 항목들을 어떤 순서로 다시 물을지 — 진행 골격 순서, 슬롯 단위 중복 제거. */
export function reaskQueueFor(
  items: readonly StrategyItem[],
  clearedIds: readonly string[],
): StrategyItemSlot[] {
  const drop = new Set(clearedIds);
  const queue: StrategyItemSlot[] = [];
  for (const item of items) {
    if (!drop.has(item.id)) continue;
    if (!queue.includes(item.slot)) queue.push(item.slot);
  }
  return queue;
}
