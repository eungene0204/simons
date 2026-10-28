import type { ParsedSummary } from "@/lib/strategy-summary";
import { t } from "@/lib/i18n";
import { itemsForStage, type PipelineStage } from "@/components/strategy/lab/labGraph";
import type { EditableField, EditableItem } from "@/components/strategy/lab/StrategyCanvas";
import { promptForSlot } from "./backtestReadiness";
import { applyDeterministicConditionChoice, type DeterministicConditionChoice } from "./deterministicConditionFlow";
import { listStrategyItems, type StrategyItemSlot } from "./strategyItems";

// 캔버스 상세 패널의 값 편집 — 사용자가 칸에 직접 넣은 숫자·고른 선택지로 전략 필드를 바꾼다(원문 해석 없음).
// 정해진 선택지(투자 대상·리밸런싱·기간)는 되묻기 칩=값 결속 표로, 숫자는 그 필드에 그대로 넣는다.

type SignalKey = "value" | "period" | "short_period" | "long_period" | "lookback_period";
const SIGNAL_FIELDS: Array<{ key: SignalKey; label: string; integer: boolean }> = [
  { key: "value", label: "기준값", integer: false },
  { key: "period", label: "기간(일)", integer: true },
  { key: "short_period", label: "단기 기간(일)", integer: true },
  { key: "long_period", label: "장기 기간(일)", integer: true },
  { key: "lookback_period", label: "관찰 기간(일)", integer: true },
];

const CHOICE_SLOTS: Partial<Record<string, StrategyItemSlot>> = {
  universe: "universe",
  rebalancing: "rebalancing",
  rebalance_method: "rebalance_method",
  backtest_period: "backtest_period",
};

const SCALAR_FIELDS: Record<string, { field: keyof ParsedSummary; label: string; min: number; max: number; integer: boolean }> = {
  max_positions: { field: "max_positions", label: "최대 종목 수", min: 1, max: 100, integer: true },
  hold_period: { field: "hold_period_days", label: "보유 기간(일)", min: 1, max: 2520, integer: true },
  stop_loss: { field: "stop_loss_pct", label: "손절(%)", min: 0.1, max: 99, integer: false },
  take_profit: { field: "take_profit_pct", label: "익절(%)", min: 0.1, max: 1000, integer: false },
  trailing_stop: { field: "trailing_stop_pct", label: "트레일링 스탑(%)", min: 0.1, max: 99, integer: false },
  initial_capital: { field: "initial_capital", label: "초기 자본(원)", min: 1, max: 1e13, integer: true },
};

function choiceOptions(slot: StrategyItemSlot, parsed: ParsedSummary) {
  return promptForSlot(slot, parsed)
    .suggestions.map((choice) => ({ choice, result: applyDeterministicConditionChoice({ parsed, condition: promptForSlot(slot, parsed), choice }) }))
    .filter((o): o is { choice: string; result: DeterministicConditionChoice } => !!o.result && !o.result.declinedField);
}

/** 고른 선택지 중 지금 전략과 같은 결과를 내는 것(현재 값 표시용). */
function currentChoice(parsed: ParsedSummary, options: ReturnType<typeof choiceOptions>): string {
  const now = JSON.stringify(parsed);
  return options.find((o) => JSON.stringify(o.result.parsed) === now)?.choice ?? "";
}

function signalAt(parsed: ParsedSummary, id: string) {
  const [kind, index] = id.split(".");
  const list = kind === "entry" ? parsed.entry_signals : kind === "exit" ? parsed.exit_signals : null;
  return list ? { kind: kind as "entry" | "exit", index: Number(index), signal: list[Number(index)] } : null;
}

function fieldsFor(parsed: ParsedSummary, id: string): EditableField[] {
  const choiceSlot = CHOICE_SLOTS[id];
  if (choiceSlot) {
    const options = choiceOptions(choiceSlot, parsed);
    return [{ key: "choice", label: t("선택"), kind: "choice", value: currentChoice(parsed, options), options: options.map((o) => ({ value: o.choice, label: t(o.choice) })) }];
  }
  const scalar = SCALAR_FIELDS[id];
  if (scalar) {
    const value = parsed[scalar.field];
    return typeof value === "number"
      ? [{ key: String(scalar.field), label: t(scalar.label), kind: "number", value, min: scalar.min, max: scalar.max, integer: scalar.integer }]
      : [];
  }
  if (id.startsWith("fundamental.")) {
    const filter = parsed.fundamental_filters[Number(id.split(".")[1])];
    return filter ? [{ key: "value", label: t("기준값"), kind: "number", value: filter.value, integer: false }] : [];
  }
  const at = signalAt(parsed, id);
  if (at?.signal) {
    return SIGNAL_FIELDS.filter(({ key }) => typeof at.signal[key] === "number").map(({ key, label, integer }) => ({
      key,
      label: t(label),
      kind: "number" as const,
      value: at.signal[key] as number,
      min: integer ? 1 : undefined,
      integer,
    }));
  }
  return [];
}

function toEditable(parsed: ParsedSummary, items: ReturnType<typeof listStrategyItems>): EditableItem[] {
  return items
    .map((item) => ({ id: item.id, label: t(item.label), value: t(item.value), fields: fieldsFor(parsed, item.id) }))
    .filter((item) => item.fields.length > 0);
}

/** 칸에 속한 전략 항목과 각 항목의 편집 칸(칸 노드를 더블클릭했을 때). 편집할 값이 없는 항목은 뺀다. */
export function editableItemsForStage(stage: PipelineStage, parsed: ParsedSummary | null): EditableItem[] {
  if (!parsed) return [];
  return toEditable(parsed, itemsForStage(stage, listStrategyItems(parsed)));
}

// 노드 경로(그래프 변환기가 붙인 스냅샷 내부 경로) → 전략 항목. 엔진 요청의 설정 칸은 이름이 1:1이다.
const REQUEST_SETTING_ITEM: Record<string, string> = {
  "snapshot.request.universe_id": "universe",
  "snapshot.request.risk.stop_loss_pct": "stop_loss",
  "snapshot.request.risk.take_profit_pct": "take_profit",
  "snapshot.request.risk.trailing_stop_pct": "trailing_stop",
  "snapshot.request.risk.max_positions": "max_positions",
  "snapshot.request.risk.rebalancing_period": "rebalancing",
  "snapshot.request.risk.rebalance_method": "rebalance_method",
  "snapshot.request.risk.init_cash": "initial_capital",
  "snapshot.request.risk.max_holding_days": "hold_period",
  "snapshot.request.period": "backtest_period",
  "snapshot.parsed.hold_period_days": "hold_period",
};

const CONDITION_REF = /^snapshot\.request\.(entry|exit)\.conditions\[(\d+)\]$/;

type RequestCondition = { id?: string; type?: string; params?: Record<string, unknown> };

/** 엔진 조건 하나가 전략의 어느 항목에서 왔는가 — 지표 id와 값이 같은 항목을 차례로 짝짓는다. 엔진이 따로
 *  덧붙인 조건(전략 항목이 없는 것)은 null이다. 구조화된 두 값을 대조할 뿐 문장을 읽지 않는다. */
function itemIdForCondition(parsed: ParsedSummary, side: "entry" | "exit", conditions: RequestCondition[], index: number): string | null {
  const taken = new Set<string>();
  const same = (a: unknown, b: unknown) => a === undefined || a === null || b === undefined || b === null || a === b;
  for (let i = 0; i <= index; i += 1) {
    const c = conditions[i];
    if (!c) return null;
    const params = c.params ?? {};
    let found: string | null = null;
    if (side === "entry" && c.type === "filter") {
      const k = parsed.fundamental_filters.findIndex(
        (f, j) => !taken.has(`fundamental.${j}`) && f.metric === c.id && same(f.value, params.value) && same(f.operator, params.operator),
      );
      if (k >= 0) found = `fundamental.${k}`;
    }
    if (!found) {
      const signals = side === "entry" ? parsed.entry_signals : parsed.exit_signals;
      const k = signals.findIndex(
        (s, j) =>
          !taken.has(`${side}.${j}`) &&
          s.indicator === c.id &&
          same(s.value, params.value) &&
          same(s.period, params.period) &&
          same(s.mode, params.mode),
      );
      if (k >= 0) found = `${side}.${k}`;
    }
    if (found) taken.add(found);
    if (i === index) return found;
  }
  return null;
}

/** 더블클릭한 노드의 편집 칸 — 조건 노드는 그 조건의 항목 하나만, 칸 노드(경로 없음)는 칸 전체. */
export function editableItemsForNode(
  stage: PipelineStage,
  sourceRef: string | null,
  parsed: ParsedSummary | null,
  request: { entry?: { conditions?: RequestCondition[] } | null; exit?: { conditions?: RequestCondition[] } | null } | null | undefined,
): EditableItem[] {
  if (!parsed) return [];
  if (!sourceRef) return editableItemsForStage(stage, parsed);
  const match = CONDITION_REF.exec(sourceRef);
  const id = match
    ? itemIdForCondition(parsed, match[1] as "entry" | "exit", request?.[match[1] as "entry" | "exit"]?.conditions ?? [], Number(match[2]))
    : REQUEST_SETTING_ITEM[sourceRef] ?? null;
  if (!id) return [];
  return toEditable(parsed, listStrategyItems(parsed).filter((item) => item.id === id));
}

function validNumber(value: unknown, field: EditableField): value is number {
  if (field.kind !== "number" || typeof value !== "number" || !Number.isFinite(value)) return false;
  if (field.integer && !Number.isInteger(value)) return false;
  if (field.min !== undefined && value < field.min) return false;
  if (field.max !== undefined && value > field.max) return false;
  return true;
}

export type ItemEdit = { slot: StrategyItemSlot; choice: DeterministicConditionChoice; text: string };

/** 편집 적용 — 바꾼 전략과 명시로 기록할 슬롯, 대화 기록에 남길 문구. 값이 범위를 벗어나면 null. */
export function applyItemEdit(parsed: ParsedSummary, id: string, changes: Record<string, number | string>): ItemEdit | null {
  const item = listStrategyItems(parsed).find((i) => i.id === id);
  if (!item) return null;
  const fields = fieldsFor(parsed, id);
  let next: ParsedSummary = parsed;
  let extra: Omit<DeterministicConditionChoice, "parsed"> = {};

  const choiceSlot = CHOICE_SLOTS[id];
  if (choiceSlot) {
    const option = choiceOptions(choiceSlot, parsed).find((o) => o.choice === changes.choice);
    if (!option) return null;
    ({ parsed: next, ...extra } = option.result);
  } else {
    for (const [key, raw] of Object.entries(changes)) {
      const field = fields.find((f) => f.key === key);
      if (!field || !validNumber(raw, field)) return null;
      if (SCALAR_FIELDS[id]) {
        next = { ...next, [SCALAR_FIELDS[id].field]: raw, ...(id === "max_positions" ? { max_positions_explicit: true } : {}) };
      } else if (id.startsWith("fundamental.")) {
        const index = Number(id.split(".")[1]);
        next = { ...next, fundamental_filters: next.fundamental_filters.map((f, i) => (i === index ? { ...f, value: raw } : f)) };
      } else {
        const at = signalAt(next, id);
        if (!at) return null;
        const listKey = at.kind === "entry" ? "entry_signals" : "exit_signals";
        next = { ...next, [listKey]: next[listKey].map((s, i) => (i === at.index ? { ...s, [key]: raw } : s)) };
      }
    }
  }
  if (next === parsed) return null;
  const updated = listStrategyItems(next).find((i) => i.id === id);
  return {
    slot: item.slot,
    choice: { ...extra, parsed: next },
    text: updated ? `${t(updated.label)} ${t(updated.value)}` : t(item.label),
  };
}
