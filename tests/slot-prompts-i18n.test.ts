import { describe, expect, it } from "vitest";

import slotPrompts from "@/app/analytics/new/__fixtures__/slot-prompts.json";
import { en } from "@/lib/i18n/en";

// 슬롯 되묻기 문구·칩의 **정본은 백엔드 한국어**이고, /us 표시 번역은 프론트 t()가 맡는다
// (되묻기 문구 계약). 그런데 이 문구들은 소스의 t() 호출이 아니라 픽스처(JSON)에서 오므로
// 기존 i18n 커버리지 테스트(소스 스캔)가 보지 못한다 — 실제로 리밸런싱 방식 질문이 사전에
// 없는 채로 /us에 나갈 뻔했다(2026-08-27). 한글이 든 문자열은 전부 사전을 요구한다.
// ETF·"$10,000" 같은 언어 중립 리터럴은 번역 대상이 아니므로 자연히 제외된다.
const HANGUL = /[가-힣]/;

function collect(node: unknown, path: string, out: Array<[string, string]>): void {
  if (!node || typeof node !== "object") return;
  const record = node as Record<string, unknown>;
  if (typeof record.question === "string" && Array.isArray(record.suggestions)) {
    out.push([`${path}.question`, record.question]);
    for (const chip of record.suggestions as string[]) out.push([`${path}.chip`, chip]);
    return;
  }
  for (const [key, value] of Object.entries(record)) collect(value, `${path}.${key}`, out);
}

describe("슬롯 되묻기 문구 — 영어 사전 커버리지", () => {
  it("한글이 든 질문·칩은 모두 영어 사전에 있다", () => {
    const entries: Array<[string, string]> = [];
    collect(slotPrompts, "", entries);
    expect(entries.length).toBeGreaterThan(10);

    const missing = entries
      .filter(([, text]) => HANGUL.test(text))
      .filter(([, text]) => !(text in en))
      .map(([path, text]) => `${path}: ${text.slice(0, 40)}`);
    expect(missing, `영어 사전(lib/i18n/en.ts) 누락:\n${missing.join("\n")}`).toEqual([]);
  });
});
