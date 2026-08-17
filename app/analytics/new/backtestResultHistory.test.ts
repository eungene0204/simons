import { afterEach, describe, expect, it, vi } from "vitest";

import { installBacktestResultBackHandler } from "./backtestResultHistory";

function makeFakeWindow() {
  const listeners: Record<string, Array<() => void>> = {};
  return {
    history: { pushState: vi.fn(), scrollRestoration: "auto" as History["scrollRestoration"] },
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

  it("turns off browser scroll restoration for the chat entry before pushing, and restores it on cleanup", () => {
    // 뒤로가기로 대화 항목에 돌아올 때 브라우저가 저장된 스크롤(실행 버튼 자리)을 되살려
    // '맨 위' 복귀를 덮던 문제(2026-08-17 Chrome 실측). manual은 push 전에 걸려야 대화 항목에 붙는다.
    const win = makeFakeWindow();
    win.history.pushState.mockImplementation(() => {
      expect(win.history.scrollRestoration).toBe("manual");
    });

    const cleanup = installBacktestResultBackHandler(() => {}, win as any);

    expect(win.history.pushState).toHaveBeenCalledOnce();
    expect(win.history.scrollRestoration).toBe("manual");
    cleanup();
    expect(win.history.scrollRestoration).toBe("auto");
  });
});
