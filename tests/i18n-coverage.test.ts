import { describe, expect, it } from "vitest";
import { createRequire } from "module";
import path from "path";
import { en } from "@/lib/i18n/en";

// 사전 커버리지 게이트 — 소스에서 t("…")로 감싼 모든 한국어 원문과, 렌더 지점에서 t(x)로
// 번역되는 상수 파일(칩·질문·라벨 맵)의 한국어 문자열이 lib/i18n/en.ts에 있어야 한다.
// 키 추출 규칙은 scripts/i18n_extract_keys.js 하나다(테스트와 스크립트가 같은 함수를 쓴다).
const require = createRequire(import.meta.url);
const { extract } = require(path.join(process.cwd(), "scripts/i18n_extract_keys.js")) as {
  extract: () => Map<string, Set<string>>;
};

// 표시 문자열이 아닌 것 — 정규식 조각·CSS(styled-jsx) 블록. 사전에 둘 이유가 없다.
function isNoise(key: string): boolean {
  return /\\[sdw]|\(\?:|\\d\+/.test(key) || key.trimStart().startsWith(".") || key.includes("@keyframes");
}

describe("i18n 사전 커버리지", () => {
  const keys = extract();

  it("소스의 모든 표시 키가 영어 사전에 있다", () => {
    const missing: string[] = [];
    for (const [key, files] of keys) {
      if (isNoise(key)) continue;
      if (!Object.prototype.hasOwnProperty.call(en, key)) {
        missing.push(`${key}  ← ${Array.from(files)[0]}`);
      }
    }
    expect(missing, `영어 사전(lib/i18n/en.ts)에 없는 키 ${missing.length}개:\n${missing.join("\n")}`).toEqual([]);
  });

  it("사전 값의 자리표시자({0}…)는 키와 같다", () => {
    const bad: string[] = [];
    for (const [key, value] of Object.entries(en)) {
      const pk = (key.match(/\{\d+\}/g) ?? []).sort().join(",");
      const pv = (value.match(/\{\d+\}/g) ?? []).sort().join(",");
      if (pk !== pv) bad.push(`${key} => ${value}`);
    }
    expect(bad).toEqual([]);
  });

  it("사전 값에 한글이 남아 있지 않다(번역 누락 방지)", () => {
    const leftovers = Object.entries(en).filter(([, value]) => /[가-힣]/.test(value));
    expect(leftovers.map(([k, v]) => `${k} => ${v}`)).toEqual([]);
  });
});
