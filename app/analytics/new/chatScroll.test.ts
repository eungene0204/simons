import { describe, expect, it, vi } from "vitest";

import { scrollChatViewToTop } from "./chatScroll";

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
