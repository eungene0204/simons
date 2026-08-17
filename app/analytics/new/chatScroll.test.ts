import { describe, expect, it, vi } from "vitest";

import {
  CHAT_INPUT_CLEARANCE,
  computeChatScrollDelta,
  scrollChatViewToEnd,
  scrollChatViewToTop,
} from "./chatScroll";

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

describe("scrollChatViewToEnd", () => {
  const doc = (main: unknown, docHeight = 3000) =>
    ({
      querySelector: () => main,
      documentElement: { scrollHeight: docHeight },
    }) as unknown as Document;

  it("scrolls the layout main container to its end when it is the scroller", () => {
    const mainScrollTo = vi.fn();
    const windowScrollTo = vi.fn();

    scrollChatViewToEnd(
      doc({ scrollHeight: 2400, clientHeight: 800, scrollTo: mainScrollTo }),
      { scrollTo: windowScrollTo } as unknown as Window
    );

    expect(mainScrollTo).toHaveBeenCalledWith({ top: 2400, behavior: "auto" });
    expect(windowScrollTo).not.toHaveBeenCalled();
  });

  it("scrolls the window to the document end when main does not scroll", () => {
    const mainScrollTo = vi.fn();
    const windowScrollTo = vi.fn();

    // main이 flex 레이아웃에서 늘어나 내부 스크롤이 없는 경우(실측 기본형).
    scrollChatViewToEnd(
      doc({ scrollHeight: 800, clientHeight: 800, scrollTo: mainScrollTo }, 3000),
      { scrollTo: windowScrollTo } as unknown as Window
    );

    expect(mainScrollTo).not.toHaveBeenCalled();
    expect(windowScrollTo).toHaveBeenCalledWith({ top: 3000, behavior: "auto" });
  });

  it("still scrolls the window when the main container is absent", () => {
    const windowScrollTo = vi.fn();

    expect(() =>
      scrollChatViewToEnd(doc(null, 1500), { scrollTo: windowScrollTo } as unknown as Window)
    ).not.toThrow();
    expect(windowScrollTo).toHaveBeenCalledWith({ top: 1500, behavior: "auto" });
  });
});

describe("scrollChatViewToTop", () => {
  const doc = (main: unknown) => ({ querySelector: () => main }) as unknown as Document;

  it("scrolls the layout main container to the top when it is the scroller", () => {
    const mainScrollTo = vi.fn();
    const windowScrollTo = vi.fn();

    scrollChatViewToTop(
      doc({ scrollHeight: 2400, clientHeight: 800, scrollTo: mainScrollTo }),
      { scrollTo: windowScrollTo } as unknown as Window
    );

    expect(mainScrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    expect(windowScrollTo).not.toHaveBeenCalled();
  });

  it("scrolls the window to the top when main does not scroll or is absent", () => {
    const mainScrollTo = vi.fn();
    const windowScrollTo = vi.fn();

    scrollChatViewToTop(
      doc({ scrollHeight: 800, clientHeight: 800, scrollTo: mainScrollTo }),
      { scrollTo: windowScrollTo } as unknown as Window
    );
    scrollChatViewToTop(doc(null), { scrollTo: windowScrollTo } as unknown as Window);

    expect(mainScrollTo).not.toHaveBeenCalled();
    expect(windowScrollTo).toHaveBeenCalledTimes(2);
    expect(windowScrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
  });
});
