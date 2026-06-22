import { describe, expect, it } from "vitest";

import { CHAT_INPUT_CLEARANCE, computeChatScrollDelta } from "./chatScroll";

describe("computeChatScrollDelta", () => {
  it("returns the distance needed when the message end is hidden behind the fixed input", () => {
    // 메시지 끝(900)이 (뷰포트 1000 - 여유 180 = 820) 아래에 있으므로 80만큼 내려야 한다.
    expect(computeChatScrollDelta(900, 1000, 180)).toBe(80);
  });

  it("returns 0 when the message end is already above the clearance (avoids over-scrolling up)", () => {
    // 메시지 끝(500)이 여유 안쪽이면 스크롤하지 않는다 — 상단이 잘리는 회귀를 막는다.
    expect(computeChatScrollDelta(500, 1000, 180)).toBe(0);
  });

  it("returns 0 exactly at the clearance boundary", () => {
    expect(computeChatScrollDelta(820, 1000, 180)).toBe(0);
  });

  it("defaults to CHAT_INPUT_CLEARANCE when clearance is omitted", () => {
    expect(computeChatScrollDelta(1000, 1000)).toBe(CHAT_INPUT_CLEARANCE);
  });
});
