import { afterEach, describe, expect, it, vi } from "vitest";

import { installBacktestResultBackHandler } from "./backtestResultHistory";

function makeFakeWindow() {
  const listeners: Record<string, Array<() => void>> = {};
  return {
    history: { pushState: vi.fn() },
    addEventListener: vi.fn((type: string, cb: () => void) => {
      (listeners[type] ??= []).push(cb);
    }),
    removeEventListener: vi.fn((type: string, cb: () => void) => {
      listeners[type] = (listeners[type] ?? []).filter((fn) => fn !== cb);
    }),
    fire(type: string) {
      (listeners[type] ?? []).forEach((fn) => fn());
    },
  };
}

describe("installBacktestResultBackHandler", () => {
  afterEach(() => vi.restoreAllMocks());

  it("pushes a history entry so the browser back button has something to pop", () => {
    const win = makeFakeWindow();

    installBacktestResultBackHandler(() => {}, win as any);

    expect(win.history.pushState).toHaveBeenCalledOnce();
    expect(win.history.pushState).toHaveBeenCalledWith(
      { simonsBacktestResult: true },
      ""
    );
  });

  it("invokes onBack when the user presses back (popstate)", () => {
    const win = makeFakeWindow();
    const onBack = vi.fn();

    installBacktestResultBackHandler(onBack, win as any);
    win.fire("popstate");

    expect(onBack).toHaveBeenCalledOnce();
  });

  it("removes the popstate listener on cleanup so it no longer fires", () => {
    const win = makeFakeWindow();
    const onBack = vi.fn();

    const cleanup = installBacktestResultBackHandler(onBack, win as any);
    cleanup();
    win.fire("popstate");

    expect(onBack).not.toHaveBeenCalled();
  });
});
