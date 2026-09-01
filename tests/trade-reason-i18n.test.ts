import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { en } from "@/lib/i18n/en";
import { REASON_TEMPLATE } from "@/lib/trade-reason";

/**
 * 매매사유 번역 게이트.
 *
 * 거래 내역의 매매사유는 엔진이 만드는 표시 문구다. 값이 박힌 완성 문장은 사전 키가 될 수
 * 없으므로 백엔드는 한국어 정본 템플릿 + 인자만 싣고(backend/engine/trade_reason.py),
 * 표시 번역은 프론트 t()가 한다. 새 템플릿을 추가하면 lib/i18n/en.ts에 같은 원문이 키로
 * 있어야 한다 — 없으면 /us에서 그 줄만 한국어로 나온다.
 */
const REASON_SOURCE = path.join(process.cwd(), "backend", "engine", "trade_reason.py");
const SIGNALS_SOURCE = path.join(process.cwd(), "backend", "engine", "signals.py");

/** 모듈 최상위의 `NAME = "한국어 정본"` 상수만 읽는다(주석·함수 본문은 대상이 아니다). */
function canonicalReasonTemplates(): string[] {
  const source = fs.readFileSync(REASON_SOURCE, "utf-8");
  const templates: string[] = [];
  for (const line of source.split("\n")) {
    const match = line.match(/^[A-Z][A-Z0-9_]* = "(.*)"$/);
    if (match && /[가-힣]/.test(match[1])) templates.push(match[1]);
  }
  return templates;
}

/** 재무 지표 라벨(FUNDAMENTAL_LABELS)도 사유에 인자로 꽂힌다 — 같은 게이트 대상이다. */
function fundamentalLabels(): string[] {
  const source = fs.readFileSync(SIGNALS_SOURCE, "utf-8");
  const block = source.slice(
    source.indexOf("FUNDAMENTAL_LABELS = {"),
    source.indexOf("FUNDAMENTAL_CIDS =")
  );
  return [...block.matchAll(/"[^"]+": "([^"]+)"/g)]
    .map((m) => m[1])
    .filter((label) => /[가-힣]/.test(label));
}

describe("매매사유 i18n", () => {
  const templates = canonicalReasonTemplates();
  const labels = fundamentalLabels();

  it("정본 템플릿을 읽어온다(추출 규칙이 깨지면 게이트가 통과처럼 보이는 것을 막는다)", () => {
    expect(templates.length).toBeGreaterThanOrEqual(60);
    expect(templates).toContain("전략 매도 조건 충족");
    expect(templates).toContain("{0}일 신고가 돌파");
    expect(labels.length).toBeGreaterThanOrEqual(10);
  });

  it("모든 사유 템플릿이 영어 사전에 있다", () => {
    const missing = [...templates, ...labels].filter(
      (template) => !Object.prototype.hasOwnProperty.call(en, template)
    );
    expect(
      missing,
      `lib/i18n/en.ts에 없는 매매사유 문구 ${missing.length}개:\n${missing.join("\n")}`
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

  it("프론트가 이름으로 아는 템플릿이 백엔드 정본과 같다", () => {
    // 백엔드에서 문구가 바뀌면 프론트의 판별(일반 매도 → 청산 조건 서술, 52주 표기)이
    // 조용히 멈춘다. 정본에 같은 문자열이 있는지 여기서 붙잡는다.
    for (const template of Object.values(REASON_TEMPLATE)) {
      expect(templates, `backend/engine/trade_reason.py에 없는 템플릿: ${template}`).toContain(
        template
      );
    }
  });
});
