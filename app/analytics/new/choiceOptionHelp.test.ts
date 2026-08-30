import { describe, expect, it } from "vitest";

import slotPrompts from "./__fixtures__/slot-prompts.json";
import {
  CHOICE_OPTION_HELP,
  HELP_BUBBLE_WIDTH,
  choiceOptionHelp,
  helpBubbleWidth,
  placeHelpBubble,
} from "./choiceOptionHelp";

type Prompt = { question?: string; suggestions: string[] };

function canonicalChips(): string[] {
  const prompts = slotPrompts as {
    slots: Record<string, Prompt>;
    variants: Record<string, Record<string, Prompt>>;
  };
  const chips = Object.values(prompts.slots).flatMap((p) => p.suggestions);
  for (const variant of Object.values(prompts.variants)) {
    for (const prompt of Object.values(variant)) chips.push(...prompt.suggestions);
  }
  return Array.from(new Set(chips));
}

describe("선택 칩 설명 정본", () => {
  // 칩 문구가 바뀌면 설명이 조용히 사라진다(키가 칩 문자열이므로). 정본 칩 목록과
  // 대조해 두면 문구를 바꾼 그 커밋에서 드러난다.
  it("백엔드 정본 슬롯 칩에는 모두 설명이 있다", () => {
    const missing = canonicalChips().filter((chip) => !choiceOptionHelp(chip));
    expect(missing).toEqual([]);
  });

  it("설명이 없는 칩에는 undefined를 돌려준다(아이콘 미표시)", () => {
    expect(choiceOptionHelp("직접 입력")).toBeUndefined();
    expect(choiceOptionHelp("2차전지 테마")).toBeUndefined();
  });

  // 설명은 사실 서술이다 — 어느 선택지가 낫다·유리하다는 판단은 규제 안전 원칙 위반이다.
  it("설명에 추천·전망 표현이 없다", () => {
    const banned = /추천|권장|유망|유리|기대됩니다|좋습니다|적합합니다|보장/;
    const offenders = Object.entries(CHOICE_OPTION_HELP)
      .filter(([, help]) => banned.test(help))
      .map(([chip]) => chip);
    expect(offenders).toEqual([]);
  });
});

describe("설명 풍선 자리잡기", () => {
  const trigger = { top: 300, left: 200, right: 220 };
  const height = 90;

  it("아이콘 바로 오른쪽 위에 놓는다", () => {
    const { top, left, width } = placeHelpBubble(trigger, 1440, 900, height);
    expect(left).toBe(trigger.right + 8);
    // 윗변이 아이콘보다 살짝 위 — 칩 윗변과 나란히 서서 '오른쪽 위'로 읽힌다.
    expect(top).toBe(trigger.top - 6);
    expect(width).toBe(HELP_BUBBLE_WIDTH);
  });

  it("오른쪽이 모자라면 왼쪽으로 넘긴다", () => {
    const { left } = placeHelpBubble({ ...trigger, left: 700, right: 720 }, 800, 900, height);
    expect(left).toBe(700 - 8 - HELP_BUBBLE_WIDTH);
  });

  // 되묻기 카드는 화면 하단에 고정된다 — 아래쪽 칩의 풍선이 화면 밖으로 나가면 잘린다.
  it("화면 아래 칩의 풍선을 화면 안으로 당긴다", () => {
    const { top } = placeHelpBubble({ ...trigger, top: 860 }, 1440, 900, height);
    expect(top + height).toBeLessThanOrEqual(900);
  });

  // 예산으로 세로 중앙을 맞추던 때는 실제보다 높이를 크게 잡아 풍선이 칩보다 한참 위에
  // 떴다(2026-08-29 신고). 높이는 잰 값만 쓰고, 자리는 높이와 무관하게 아이콘이 정한다.
  it("풍선 높이가 달라도 윗변 위치는 그대로다", () => {
    const short = placeHelpBubble(trigger, 1440, 900, 40);
    const tall = placeHelpBubble(trigger, 1440, 900, 180);
    expect(short.top).toBe(tall.top);
  });

  it("좁은 화면에서는 폭을 화면에 맞춘다", () => {
    const { left, width } = placeHelpBubble({ ...trigger, left: 20, right: 300 }, 320, 700, height);
    expect(width).toBe(helpBubbleWidth(320));
    expect(left).toBeGreaterThanOrEqual(0);
    expect(left + width).toBeLessThanOrEqual(320);
  });
});
