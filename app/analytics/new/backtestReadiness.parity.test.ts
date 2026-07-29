import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import { getNextMissingBacktestCondition } from "./backtestReadiness";
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
  expectedMissingField: string | null;
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
        requireExplicitConfiguration: true,
      },
    );
    expect(missing?.field ?? null).toBe(testCase.expectedMissingField);
  });
});
