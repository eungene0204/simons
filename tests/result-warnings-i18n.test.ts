import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { en } from "@/lib/i18n/en";

/**
 * 백테스트 결과 경고 번역 게이트.
 *
 * 사고(2026-09-03): /us 백테스트 결과 로그에 "리밸런싱일에는 그날 매수 조건을 충족한 종목
 * 중에서 …"가 한국어 그대로 나왔다. 결과 경고는 엔진이 값을 박아 만든 완성 문장이라 사전
 * 키가 될 수 없었고(값마다 키가 달라짐), 값 없는 문장도 사전에 빠져 있었다.
 *
 * 계약: backend/engine/result_warnings.py가 경고의 한국어 정본 템플릿을 모두 보유하고,
 * 엔진은 warnings(한국어)와 warningParts(템플릿+인자)를 같은 순서로 싣는다. 표시 번역은
 * 프론트 t()가 한다. 새 템플릿을 추가하면 lib/i18n/en.ts에도 같은 원문이 키로 있어야 한다.
 */
const SOURCE = path.join(process.cwd(), "backend", "engine", "result_warnings.py");

/** 모듈 최상위의 `NAME = "한국어 정본"` 상수만 읽는다(주석·함수 본문은 대상이 아니다). */
function canonicalWarningTemplates(): string[] {
  const source = fs.readFileSync(SOURCE, "utf-8");
  const templates: string[] = [];
  for (const line of source.split("\n")) {
    const match = line.match(/^[A-Z][A-Z0-9_]* = "(.*)"$/);
    if (match && /[가-힣]/.test(match[1])) templates.push(match[1]);
  }
  return templates;
}

describe("백테스트 결과 경고 i18n", () => {
  const templates = canonicalWarningTemplates();

  it("정본 템플릿을 읽어온다(추출 규칙이 깨지면 게이트가 통과처럼 보이는 것을 막는다)", () => {
    expect(templates.length).toBeGreaterThanOrEqual(45);
    expect(templates).toContain(
      "리밸런싱일에는 그날 매수 조건을 충족한 종목 중에서 포트폴리오를 다시 구성합니다(충족하지 않는 보유 종목은 편출) — 그 사이 날에도 매수 조건 충족 종목을 빈 자리만큼 담고 매도 조건은 그대로 적용합니다. 유지 종목의 비중은 목표 비중으로 리셋되지 않습니다."
    );
    expect(templates).toContain("거래 수가 {0}건으로 30건 미만입니다 — 승률·Profit Factor 등 통계의 표본 신뢰도가 낮습니다.");
  });

  it("모든 경고 템플릿이 영어 사전에 있다", () => {
    const missing = templates.filter(
      (template) => !Object.prototype.hasOwnProperty.call(en, template)
    );
    expect(
      missing,
      `lib/i18n/en.ts에 없는 결과 경고 문구 ${missing.length}개:\n${missing.join("\n")}`
    ).toEqual([]);
  });

  it("자리표시자({0}…)가 원문과 번역에서 같다", () => {
    const bad = templates
      .filter((template) => en[template])
      .filter((template) => {
        const inKey = (template.match(/\{\d+\}/g) ?? []).sort().join(",");
        const inValue = (en[template].match(/\{\d+\}/g) ?? []).sort().join(",");
        return inKey !== inValue;
      });
    expect(bad).toEqual([]);
  });
});
