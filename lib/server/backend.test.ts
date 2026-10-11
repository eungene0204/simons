/**
 * fetchBackend — 호출자의 AbortSignal 전파.
 *
 * 라우트가 req.signal(클라이언트 연결 종료 시 abort)을 넘기면 백엔드 연결도 함께 끊겨야
 * '대화 종료'가 서버 쪽 작업(LLM 파싱 등)까지 멈춘다. 예전엔 timeoutMs용 signal이 호출자
 * signal을 덮어써서 백엔드 연결이 예산이 다할 때까지 살아 있었다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const undiciFetch = vi.fn();

vi.mock("undici", () => ({
  fetch: undiciFetch,
  Agent: class {},
}));

const { fetchBackend } = await import("./backend");

describe("fetchBackend signal propagation", () => {
  beforeEach(() => {
    // mockReset — 실패한 테스트가 남긴 mockImplementationOnce 큐가 다음 테스트로 새지 않게.
    undiciFetch.mockReset();
    delete process.env.BACKEND_URL;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("aborts the backend request when the caller's signal aborts", async () => {
    let upstreamSignal: AbortSignal | undefined;
    undiciFetch.mockImplementationOnce((_url: string, init: { signal?: AbortSignal }) => {
      upstreamSignal = init.signal;
      return new Promise((_, reject) => {
        init.signal?.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
      });
    });

    const caller = new AbortController();
    const pending = fetchBackend("/strategy/parse-stream", {
      method: "POST",
      timeoutMs: 60_000,
      signal: caller.signal,
    });
    await vi.waitFor(() => expect(upstreamSignal).toBeInstanceOf(AbortSignal));
    expect(upstreamSignal!.aborted).toBe(false);

    caller.abort();

    expect(upstreamSignal!.aborted).toBe(true);
    await expect(pending).rejects.toThrow();
  });

  it("keeps the timeout budget alongside the caller's signal", async () => {
    vi.useFakeTimers();
    let upstreamSignal: AbortSignal | undefined;
    undiciFetch.mockImplementationOnce((_url: string, init: { signal?: AbortSignal }) => {
      upstreamSignal = init.signal;
      return new Promise(() => {});
    });

    const caller = new AbortController();
    void fetchBackend("/query/classify", { timeoutMs: 1_000, signal: caller.signal }).catch(() => {});
    await vi.waitFor(() => expect(upstreamSignal).toBeInstanceOf(AbortSignal));

    await vi.advanceTimersByTimeAsync(1_500);
    expect(upstreamSignal!.aborted).toBe(true);
    expect(caller.signal.aborted).toBe(false);
  });

  it("does not open a backend connection when the caller already aborted", async () => {
    const caller = new AbortController();
    caller.abort();

    await expect(
      fetchBackend("/query/classify", { timeoutMs: 1_000, signal: caller.signal })
    ).rejects.toBeDefined();
    expect(undiciFetch).not.toHaveBeenCalled();
  });

  it("works without a caller signal (timeout only)", async () => {
    undiciFetch.mockResolvedValueOnce({ ok: true });
    await expect(fetchBackend("/health", { timeoutMs: 1_000 })).resolves.toEqual({ ok: true });
    const [, init] = undiciFetch.mock.calls[0];
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});

describe("backend path confinement (2026-10-11 경로 이탈)", () => {
  beforeEach(() => {
    undiciFetch.mockReset();
    delete process.env.BACKEND_URL;
  });

  it("backendPathSegment encodes separators and rejects dot segments", async () => {
    const { backendPathSegment } = await import("./backend");
    expect(backendPathSegment("005930")).toBe("005930");
    expect(backendPathSegment("BRK.B")).toBe("BRK.B");
    expect(backendPathSegment("../../admin/trace-triage?")).toBe("..%2F..%2Fadmin%2Ftrace-triage%3F");
    expect(backendPathSegment("a#b")).toBe("a%23b");
    for (const bad of ["", ".", "..", null, undefined]) expect(backendPathSegment(bad)).toBeNull();
  });

  it("fetchBackend refuses paths with dot segments before any request", async () => {
    for (const path of ["/stock/../admin/trace-triage", "/a/%2E%2E/admin", "/research/./x", "/x/..?q=1", "/stock/..\\..\\ontology/graph"]) {
      await expect(fetchBackend(path)).rejects.toThrow(/unsafe backend path/);
    }
    expect(undiciFetch).not.toHaveBeenCalled();
    undiciFetch.mockResolvedValue(new Response("{}"));
    await fetchBackend("/stock/BRK.B/ohlcv?x=..");
    expect(undiciFetch).toHaveBeenCalledTimes(1);
  });
});
