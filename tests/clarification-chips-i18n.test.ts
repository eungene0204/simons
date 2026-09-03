import { describe, expect, it } from "vitest";
import chips from "@/app/analytics/new/__fixtures__/clarification-chips.json";
import { en } from "@/lib/i18n/en";

// 되묻기 칩의 정본은 백엔드 한국어(칩=값 결속이 한국어 표기로 확정된다)이고, /us 표시는
// 프론트 t()가 맡는다. 값이 섞인 칩("매출액증가율 10% 이상", "수익률 산정 기간 60일")은
// 소스의 t() 호출이 아니라 백엔드 조합에서 오므로 소스 스캔 커버리지 테스트가 못 본다 —
// 2026-09-03 US 영어 전수 게이트에서 이런 칩 10여 종이 한국어로 나갔다. 조합은 유한하므로
// scripts/export_clarification_chips.py가 전부 열거하고 여기서 사전을 요구한다.
const HANGUL = /[가-힣]/;

describe("되묻기 칩 — 영어 사전 커버리지", () => {
  it("픽스처를 읽어온다(추출이 깨지면 게이트가 통과처럼 보이는 것을 막는다)", () => {
    const all = Object.values(chips as Record<string, string[]>).flat();
    expect(all.length).toBeGreaterThan(80);
    expect(all).toContain("매출액증가율 10% 이상");
  });
  it("한글이 든 칩은 모두 영어 사전에 있다", () => {
    const missing = Object.entries(chips as Record<string, string[]>)
      .flatMap(([group, list]) => list.map((chip) => [group, chip] as const))
      .filter(([, chip]) => HANGUL.test(chip))
      .filter(([, chip]) => !(chip in en))
      .map(([group, chip]) => `${group}: ${chip}`);
    expect(missing, `영어 사전(lib/i18n/en.ts) 누락:\n${missing.join("\n")}`).toEqual([]);
  });
});
