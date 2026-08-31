import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { en } from "@/lib/i18n/en";

/**
 * 백테스트 진행 문구 번역 게이트.
 *
 * 사고(2026-09-01): /us에서 백테스트를 돌리면 카드 제목만 "Backtest running"이고 본문은
 * "전략 조건 계산 및 시뮬레이션 진행 중..."처럼 한국어로 나왔다. 진행 문구는 백엔드 SSE가
 * 보내는 문자열인데 표시 지점에서 t()를 거치지 않았고, 영어 사전에도 없었다.
 *
 * 계약: backend/stream_progress.py가 진행 문구의 한국어 정본을 모두 보유하고, 표시 번역은
 * 프론트 t()가 한다. 새 문구를 추가하면 lib/i18n/en.ts에도 같은 원문이 키로 있어야 한다.
 */
const SOURCE = path.join(process.cwd(), "backend", "stream_progress.py");

/** 모듈 최상위의 `NAME = "한국어 정본"` 상수만 읽는다(함수 본문·주석은 대상이 아니다). */
function canonicalProgressMessages(): string[] {
  const source = fs.readFileSync(SOURCE, "utf-8");
  const messages: string[] = [];
  for (const line of source.split("\n")) {
    const match = line.match(/^[A-Z][A-Z0-9_]* = "([^"]+)"$/);
    if (match && /[가-힣]/.test(match[1])) messages.push(match[1]);
  }
  return messages;
}

describe("백테스트 진행 문구 i18n", () => {
  const messages = canonicalProgressMessages();

  it("정본 상수를 읽어온다(추출 규칙이 깨지면 게이트가 통과처럼 보이는 것을 막는다)", () => {
    expect(messages.length).toBeGreaterThanOrEqual(7);
    expect(messages).toContain("전략 조건 계산 및 시뮬레이션 진행 중...");
  });

  it("모든 진행 문구가 영어 사전에 있다", () => {
    const missing = messages.filter(
      (message) => !Object.prototype.hasOwnProperty.call(en, message)
    );
    expect(
      missing,
      `lib/i18n/en.ts에 없는 진행 문구 ${missing.length}개:\n${missing.join("\n")}`
    ).toEqual([]);
  });

  it("자리표시자({0}…)가 원문과 번역에서 같다", () => {
    const bad = messages
      .filter((message) => en[message])
      .filter((message) => {
        const inKey = (message.match(/\{\d+\}/g) ?? []).sort().join(",");
        const inValue = (en[message].match(/\{\d+\}/g) ?? []).sort().join(",");
        return inKey !== inValue;
      });
    expect(bad).toEqual([]);
  });
});
