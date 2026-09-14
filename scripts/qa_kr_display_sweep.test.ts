/**
 * KR 예시 전략 **화면 표시** 전수 조사 — 백엔드 파싱 결과(qa_template_detect 캐시)를 요약 카드·
 * 설정 목록 렌더 코드에 그대로 통과시켜, 사용자에게 보이는 글자에 표시 결함이 없는지 본다.
 *
 * 값 검사(qa_template_detect.py)는 "백엔드가 맞게 이해했나"까지만 본다 — 2026-09-15 실측:
 * '두 달에 한 번'이 값은 정확히 bimonthly인데 카드에는 영문 'bimonthly'가 그대로 나갔다.
 * 이 조사는 그 다음 단계, "이해한 것을 화면이 맞게 보여주나"를 본다.
 *
 * 실행: QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts
 * (캐시 scripts/.template_parse_cache.json은 게이트 실행이 남긴다 — 없으면 건너뛴다)
 */
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { EXAMPLES } from "@/components/strategy/StrategyExampleTabs";
import { buildBuilderTurnPresentation } from "@/app/analytics/new/builderProgressPresentation";
import { listStrategyItems } from "@/app/analytics/new/strategyItems";
import type { ParsedSummary } from "@/lib/strategy-summary";

const CACHE = "scripts/.template_parse_cache.json";
const ENABLED = process.env.QA_DISPLAY_SWEEP === "1" && existsSync(CACHE);

// 한국어 화면에 남아도 되는 영문: 지표·시장·티커 약어(대문자), 단위. 소문자 낱말은 전부 의심한다.
const LOWER_WORD = /\b[a-z][a-z_]{2,}\b/g;
const ALLOWED_LOWER = new Set<string>();
const HARD_BAD = /undefined|null\b|NaN|\[object|\b[a-z_]+\.[a-z_]+\b/;

type Finding = { example: string; where: string; label: string; value: string; why: string };

function inspect(example: string, where: string, label: string, value: unknown, out: Finding[]) {
  const text = String(value ?? "");
  if (HARD_BAD.test(text)) out.push({ example, where, label, value: text, why: "내부값/빈값 노출" });
  const lowers = (text.match(LOWER_WORD) ?? []).filter((w) => !ALLOWED_LOWER.has(w));
  if (lowers.length) out.push({ example, where, label, value: text, why: `영문 잔존: ${lowers.join(",")}` });
}

describe.skipIf(!ENABLED)("KR 예시 화면 표시 전수 조사", () => {
  it("요약 카드·설정 목록에 영문 enum·내부 식별자·빈값이 남지 않는다", () => {
    const cache = JSON.parse(readFileSync(CACHE, "utf-8")) as Record<string, any>;
    const findings: Finding[] = [];
    let covered = 0;
    const missing: string[] = [];
    for (const ex of EXAMPLES) {
      const res = cache[ex.prompt];
      if (!res?.parsed) { missing.push(ex.title); continue; }
      covered += 1;
      const parsed = res.parsed as ParsedSummary;
      const { summaryItems, progressItems } = buildBuilderTurnPresentation({
        state: {},
        reply: String(res.clarification_question ?? ""),
        parsed,
        explicitFields: res.explicit_fields ?? [],
        backtestRequest: res.backtest_request ?? undefined,
        declinedFields: res.declined_fields ?? [],
        pendingConditions: res.pending_conditions ?? [],
      });
      for (const item of summaryItems) inspect(ex.title, "요약 카드", item.label, item.value, findings);
      for (const item of progressItems ?? []) {
        const v = (item as any).value ?? (item as any).detail ?? "";
        inspect(ex.title, "진행 패널", String((item as any).label ?? ""), v, findings);
      }
      for (const item of listStrategyItems(parsed)) inspect(ex.title, "설정 목록", item.label, item.value, findings);
      for (const n of res.notices ?? []) inspect(ex.title, "안내", "notice", n, findings);
    }
    const lines = findings.map((f) => `- [${f.example}] ${f.where} · ${f.label}: "${f.value}" ← ${f.why}`);
    console.log(`\n=== KR 화면 표시 전수 조사: 예시 ${covered}/${EXAMPLES.length} 대조, 결함 ${findings.length}건, 캐시 없음 ${missing.length}건 ===`);
    if (missing.length) console.log("캐시 없음:", missing.join(" | "));
    if (lines.length) console.log(lines.join("\n"));
    expect(covered).toBeGreaterThan(0);
    expect(findings, lines.join("\n")).toEqual([]);
  });
});
