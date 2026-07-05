// @ts-nocheck
import { afterEach, describe, expect, it, vi } from "vitest";

import { runWalkForwardStream } from "./walkForwardStream";

function sseResponse(payloads: string[]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const payload of payloads) {
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      }
      controller.close();
    },
  });
  return { ok: true, body };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("runWalkForwardStream", () => {
  it("progress 이벤트를 전달하고 result를 반환한다", async () => {
    const events = [
      JSON.stringify({ type: "progress", stage: "prepare", message: "준비" }),
      JSON.stringify({ type: "progress", stage: "window", window: 1, total: 3 }),
      JSON.stringify({ type: "result", data: { status: "ok", n_splits: 3 } }),
      "[DONE]",
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(events)));

    const progress: any[] = [];
    const result = await runWalkForwardStream({ any: "req" }, { onProgress: (e) => progress.push(e) });

    expect(result).toEqual({ status: "ok", n_splits: 3 });
    expect(progress).toHaveLength(2);
    expect(progress[1]).toMatchObject({ stage: "window", window: 1, total: 3 });
  });

  it("error 이벤트는 예외로 전파한다", async () => {
    const events = [
      JSON.stringify({ type: "error", message: "조합 수가 상한을 초과했습니다." }),
      "[DONE]",
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(events)));

    await expect(runWalkForwardStream({}, {})).rejects.toThrow("조합 수가 상한을 초과했습니다.");
  });

  it("result 없이 스트림이 끝나면 예외를 던진다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(["[DONE]"])));

    await expect(runWalkForwardStream({}, {})).rejects.toThrow("결과를 받지 못했습니다");
  });

  it("HTTP 에러 응답의 detail을 예외 메시지로 사용한다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        body: null,
        json: () => Promise.resolve({ detail: "데이터가 너무 짧습니다" }),
      })
    );

    await expect(runWalkForwardStream({}, {})).rejects.toThrow("데이터가 너무 짧습니다");
  });
});
