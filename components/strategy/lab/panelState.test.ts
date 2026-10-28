import { describe, expect, it } from "vitest";

import { LAB_PANEL_STORAGE_KEY, readLabPanels, writeLabPanels } from "./panelState";

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => Array.from(data.keys())[i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  };
}

const throwing = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
} as unknown as Storage;

describe("전략 연구소 패널 열림 상태 저장", () => {
  it("저장한 값을 그대로 읽는다", () => {
    const storage = memoryStorage();
    writeLabPanels(storage, { conversations: false, chat: false });
    expect(readLabPanels(storage)).toEqual({ conversations: false, chat: false });
  });

  it("불리언이 아닌 값·깨진 JSON은 버린다", () => {
    expect(readLabPanels(memoryStorage({ [LAB_PANEL_STORAGE_KEY]: '{"conversations":"no","chat":false}' }))).toEqual({ chat: false });
    expect(readLabPanels(memoryStorage({ [LAB_PANEL_STORAGE_KEY]: "{" }))).toEqual({});
  });

  it("저장소가 막힌 환경에서도 던지지 않는다", () => {
    expect(readLabPanels(throwing)).toEqual({});
    expect(() => writeLabPanels(throwing, { conversations: true, chat: true })).not.toThrow();
    expect(readLabPanels(undefined)).toEqual({});
  });
});
