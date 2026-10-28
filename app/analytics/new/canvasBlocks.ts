import type { ParsedSummary } from "@/lib/strategy-summary";
import type { SectionKey } from "@/lib/strategy-graph/types";
import { promptForSlot, type MissingBacktestCondition } from "./backtestReadiness";
import {
  applyDeterministicConditionChoice,
  entryChoiceKind,
  type DeterministicConditionChoice,
} from "./deterministicConditionFlow";

// 캔버스 블록 = 되묻기 칩. 칩 하나가 값 하나로 정해져 있어(칩=값 결속 계약) 블록을 올리는 즉시
// 그 값이 전략에 들어간다 — 사용자가 직접 올렸다는 것이 의도의 근거이고, 원문 해석이 없다.
// 칩 목록·값의 정본은 되묻기와 같다(slot-prompts 픽스처 + deterministicConditionFlow 표).

type Slot = MissingBacktestCondition["field"];

export type CanvasBlock = { stage: SectionKey; slot: Slot; choice: string };

/** 아무것도 정하지 않은 전략 — 백엔드 ParsedStrategy 기본값과 같다. 명시 여부는 explicitFields가
 *  따로 들고 있어, 이 값들은 '정해졌다'로 세지 않는다(실행 게이트가 다시 묻는다). */
export const EMPTY_PARSED: ParsedSummary = {
  description: "",
  universe: [],
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

const STAGE_SLOTS: Record<SectionKey, Array<{ slot: Slot; kind?: ReturnType<typeof entryChoiceKind> }>> = {
  universe: [{ slot: "universe" }],
  filters: [{ slot: "entry", kind: "filter" }],
  ranking: [{ slot: "entry", kind: "ranking" }],
  entry: [{ slot: "entry", kind: "signal" }],
  exit: [{ slot: "exit" }],
  allocation: [{ slot: "max_positions" }],
  rebalance: [{ slot: "rebalancing" }, { slot: "rebalance_method" }],
  risk: [{ slot: "stop_loss" }, { slot: "take_profit" }],
};

// 목록 칸은 블록을 더할 때 기존 조건 뒤에 잇는다(칩 답변은 빈 칸을 채우므로 교체였다).
const LIST_FIELDS = ["entry_signals", "exit_signals", "fundamental_filters"] as const;

function apply(parsed: ParsedSummary, slot: Slot, choice: string): DeterministicConditionChoice | null {
  return applyDeterministicConditionChoice({ parsed, condition: promptForSlot(slot, parsed), choice });
}

/** 칸에 올릴 수 있는 블록 — 그 칸 슬롯의 칩 중 값이 정해진 것('안 함' 거부 칩·자유 입력 제외). */
export function canvasBlocksForStage(stage: SectionKey, parsed: ParsedSummary | null): CanvasBlock[] {
  const base = parsed ?? EMPTY_PARSED;
  return STAGE_SLOTS[stage].flatMap(({ slot, kind }) =>
    promptForSlot(slot, base)
      .suggestions.filter((choice) => (kind ? entryChoiceKind(choice) === kind : true))
      .filter((choice) => {
        const result = apply(base, slot, choice);
        return !!result && !result.declinedField;
      })
      .map((choice) => ({ stage, slot, choice })),
  );
}

/** 블록을 전략에 넣는다. 목록 칸은 기존 조건 뒤에 잇고(같은 조건은 한 번만), 값 칸은 바꾼다. */
export function applyCanvasBlock(parsed: ParsedSummary | null, block: CanvasBlock): DeterministicConditionChoice | null {
  const base = parsed ?? EMPTY_PARSED;
  const result = apply(base, block.slot, block.choice);
  if (!result || result.declinedField) return null;
  const next: ParsedSummary = { ...result.parsed };
  for (const key of LIST_FIELDS) {
    const before = base[key] as unknown[];
    const after = next[key] as unknown[];
    if (after === before) continue;
    const seen = new Set(before.map((item) => JSON.stringify(item)));
    (next as unknown as Record<string, unknown>)[key] = [...before, ...after.filter((item) => !seen.has(JSON.stringify(item)))];
  }
  return { ...result, parsed: next };
}
