import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import { getNextMissingBacktestCondition } from "./backtestReadiness";
import { buildBuilderTurnPresentation } from "./builderProgressPresentation";
import fixture from "./__fixtures__/slot-judgments.json";

// 빈 슬롯 판정의 정본은 백엔드 하나다(backend/engine/strategy_slots.py).
// 프론트가 같은 판정을 다시 구현하는 이유는 하나뿐 — 칩 답변을 백엔드 왕복 없이
// 즉시 적용해야 해서다(대화 지연). 구현이 둘이면 반드시 어긋나므로(2026-07-28·07-29
// 사고 3건이 전부 이 계열이었다) 정본이 생성한 픽스처로 프론트를 고정한다.
//
// 픽스처 갱신: python scripts/export_slot_judgments.py
// 이 테스트가 깨지면 프론트 게이트를 고친다 — 픽스처를 손으로 고치지 않는다.

type SlotCase = {
  name: string;
  parsed: Record<string, unknown>;
  explicitFields: string[];
  allowNoRebalancing: boolean;
  declinedFields: string[];
  expectedMissingField: string | null;
  expectedFilledSlots: string[];
};

const cases = (fixture as { cases: SlotCase[] }).cases;

describe("빈 슬롯 판정 — 백엔드 정본과 프론트 게이트의 일치", () => {
  it("픽스처가 비어 있지 않다(생성 스크립트 누락 감지)", () => {
    expect(cases.length).toBeGreaterThan(20);
  });

  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, testCase) => {
    const missing = getNextMissingBacktestCondition(
      testCase.parsed as unknown as ParsedSummary,
      {
        explicitFields: testCase.explicitFields,
        allowNoRebalancing: testCase.allowNoRebalancing,
        declinedFields: testCase.declinedFields,
        requireExplicitConfiguration: true,
      },
    );
    expect(missing?.field ?? null).toBe(testCase.expectedMissingField);
  });
});

// 진행률 패널은 '첫 빈 슬롯'이 아니라 **슬롯별** 상태를 보여준다. 픽스처가 첫 빈 슬롯만
// 내보내던 동안 이 소비자에겐 대조할 정본이 없었고, 그래서 게이트만 고쳐지고 패널은 낡은
// 채 남았다(2026-07-29: 백테스트 창이 자동 확정됐는데 체크가 안 됨). 슬롯별 정답
// (expectedFilledSlots)으로 패널도 정본에 고정한다.
//
// 빌더 state가 있는 턴은 사용자가 직접 답한 값이 추가로 반영되므로(그 자체가 명시),
// 여기서는 state 없이 parsed만으로 판정되는 경로를 대조한다.
describe("빈 슬롯 판정 — 백엔드 정본과 프론트 진행률 패널의 일치", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, testCase) => {
    const presentation = buildBuilderTurnPresentation({
      state: {},
      reply: "",
      parsed: testCase.parsed as unknown as ParsedSummary,
      explicitFields: testCase.explicitFields,
      allowNoRebalancing: testCase.allowNoRebalancing,
      declinedFields: testCase.declinedFields,
    });
    const completed = presentation.progressItems
      .filter((item) => item.complete)
      .map((item) => item.label);
    // 패널은 '리스크 관리'를 손절·익절 각각이 아니라 하나로 묶어 보여주고, 지정 종목
    // 모드에선 '최대 보유'를 '포트폴리오'로 부른다 — 라벨 차이는 정본과 같은 어휘로 맞춘다.
    const normalized = completed.map((l) => (l === "포트폴리오" ? "최대 보유" : l));
    expect(new Set(normalized)).toEqual(new Set(testCase.expectedFilledSlots));
  });
});
