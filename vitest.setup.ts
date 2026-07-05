import '@testing-library/jest-dom';

// jsdom에는 ResizeObserver가 없어 recharts ResponsiveContainer가 크래시한다 — 최소 스텁 제공.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
