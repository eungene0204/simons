// @ts-nocheck
import { afterEach, describe, expect, it, vi } from "vitest";

import { formatApiErrorDetail, runWalkForwardStream } from "./walkForwardStream";

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

  it("pydantic 422의 detail 객체 배열은 [object Object] 대신 읽을 수 있는 메시지로 바꾼다", async () => {
    // FastAPI 검증 실패 응답 형태 — detail이 객체 배열이라 그대로 Error에 넣으면
    // "[object Object]"로 표시되던 회귀 케이스.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        body: null,
        json: () =>
          Promise.resolve({
            detail: [
              {
                type: "missing",
                loc: ["body", "base_strategy", "symbols"],
                msg: "Field required",
                input: {},
              },
            ],
          }),
      })
    );

    const error = await runWalkForwardStream({}, {}).catch((e) => e);
    expect(error.message).toBe("base_strategy.symbols: Field required");
    expect(error.message).not.toContain("[object Object]");
  });

  it("keep-alive 하트비트 주석은 무시하고 스트림을 이어간다", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(": keep-alive\n\n"));
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "progress", stage: "window", window: 1, total: 2 })}\n\n`)
        );
        controller.enqueue(encoder.encode(": keep-alive\n\n"));
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "result", data: { status: "ok" } })}\n\n`)
        );
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

    const progress: any[] = [];
    const result = await runWalkForwardStream({}, { onProgress: (e) => progress.push(e) });

    expect(result).toEqual({ status: "ok" });
    expect(progress).toHaveLength(1);
  });

  it("fetch가 network error로 실패하면 안내 메시지로 바꿔 던진다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network error")));

    await expect(runWalkForwardStream({}, {})).rejects.toThrow("서버와 연결이 끊겼습니다");
  });

  it("스트림 도중 연결이 끊기면(network error) 안내 메시지로 바꿔 던진다", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.error(new TypeError("network error"));
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

    await expect(runWalkForwardStream({}, {})).rejects.toThrow("서버와 연결이 끊겼습니다");
  });

  it("사용자 취소(AbortError)는 안내 메시지로 덮지 않고 그대로 전파한다", async () => {
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));

    await expect(runWalkForwardStream({}, {})).rejects.toBe(abortError);
  });
});

describe("formatApiErrorDetail", () => {
  it("문자열은 그대로, null/undefined는 null을 반환한다", () => {
    expect(formatApiErrorDetail("에러 메시지")).toBe("에러 메시지");
    expect(formatApiErrorDetail(null)).toBeNull();
    expect(formatApiErrorDetail(undefined)).toBeNull();
  });

  it("pydantic 검증 에러 배열은 경로: 메시지 형태로 합친다", () => {
    const detail = [
      { type: "missing", loc: ["body", "base_strategy", "symbols"], msg: "Field required" },
      { type: "int_parsing", loc: ["body", "n_trials"], msg: "Input should be a valid integer" },
    ];
    expect(formatApiErrorDetail(detail)).toBe(
      "base_strategy.symbols: Field required / n_trials: Input should be a valid integer"
    );
  });

  it("알 수 없는 객체는 JSON 문자열로 바꾼다", () => {
    expect(formatApiErrorDetail({ code: 500 })).toBe('{"code":500}');
    expect(formatApiErrorDetail([{ odd: true }])).toBe('{"odd":true}');
  });
});
