import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const fetchBackend = vi.fn();

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

const { POST } = await import("./route");

// 백엔드 /strategy/parse-stream 의 SSE 응답을 흉내내는 ReadableStream을 만든다.
function sseBackendResponse(events: Array<object | string>) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) {
        const payload = typeof event === "string" ? event : JSON.stringify(event);
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      }
      controller.close();
    },
  });
  return { ok: true, body };
}

function backendResultEvents(data: object) {
  return [
    { type: "stage", stage: "parsing" },
    { type: "result", data },
    "[DONE]",
  ];
}

function makeRequest(body: object) {
  return new NextRequest(
    new Request("http://localhost/api/strategy/parse/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

async function readEvents(response: Response) {
  const text = await response.text();
  return text
    .split("\n\n")
    .filter(Boolean)
    .map((chunk) => chunk.replace(/^data: /, ""));
}

describe("POST /api/strategy/parse/stream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("emits accepted, skeleton, and stage before final parse events", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: {
            description: "pbr 1이하 10개 1년 보유",
            universe: ["KOSPI200"],
            fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
          },
          backtest_request: {
            strategy_id: "hash_value",
            symbols: ["005930"],
            symbol_count: 1,
          },
          symbol_count: 1,
        })
      )
    );

    const response = await POST(makeRequest({ prompt: "pbr 1이하 10개 1년 보유", backend: "mlx" }));

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");

    const events = await readEvents(response);
    expect(JSON.parse(events[0])).toEqual({ type: "accepted" });
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI200"],
        max_positions: 10,
        confidence: "partial",
      },
    });
    expect(JSON.parse(events[2])).toEqual({ type: "stage", stage: "parsing" });
    expect(JSON.parse(events[3])).toMatchObject({
      type: "parsed_final",
      parsed: {
        description: "pbr 1이하 10개 1년 보유",
      },
    });
    expect(JSON.parse(events[4])).toMatchObject({
      type: "dsl_ready",
      symbol_count: 1,
    });
    expect(events[5]).toBe("[DONE]");
  });

  it("forwards a thinking stage event when the backend falls back to the LLM", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse([
        { type: "stage", stage: "parsing" },
        { type: "stage", stage: "thinking" },
        {
          type: "result",
          data: {
            parsed: { description: "복잡한 전략", universe: ["KOSPI"] },
            backtest_request: { strategy_id: "h", symbols: ["005930"], symbol_count: 1 },
            symbol_count: 1,
          },
        },
        "[DONE]",
      ])
    );

    const response = await POST(makeRequest({ prompt: "복잡한 서술형 전략", backend: "ollama" }));
    const events = await readEvents(response);
    const stages = events
      .map((e) => {
        try {
          return JSON.parse(e);
        } catch {
          return null;
        }
      })
      .filter((e) => e?.type === "stage")
      .map((e) => e.stage);
    expect(stages).toEqual(["parsing", "thinking"]);
  });

  it("uses previous parsed universe for modification skeleton when prompt omits universe", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: {
            description: "KOSPI PBR strategy",
            universe: ["KOSPI"],
            trailing_stop_pct: 15,
          },
          backtest_request: {
            strategy_id: "hash_value",
            universe_id: "kospi",
            symbols: ["005930"],
            symbol_count: 1,
          },
          symbol_count: 1,
        })
      )
    );

    const response = await POST(makeRequest({
      prompt: "트레일링 15% 추가해줘",
      backend: "mlx",
      previous_parsed: {
        universe: ["KOSPI"],
      },
    }));

    const events = await readEvents(response);
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI"],
      },
    });
  });

  it("uses explicit prompt universe over previous parsed universe", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: {
            description: "KOSPI200 strategy",
            universe: ["KOSPI200"],
          },
          backtest_request: {
            strategy_id: "hash_value",
            universe_id: "kospi200",
            symbols: ["069500"],
            symbol_count: 1,
          },
          symbol_count: 1,
        })
      )
    );

    const response = await POST(makeRequest({
      prompt: "KOSPI200으로 바꿔줘",
      backend: "mlx",
      previous_parsed: {
        universe: ["KOSPI"],
      },
    }));

    const events = await readEvents(response);
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI200"],
      },
    });
  });

  it("forwards a deferred validation correction as a parsed_updated event", async () => {
    // 비차단 검증: 백엔드가 result를 먼저 보내고, 후행 LLM 검증 교정본을 result_update로
    // 후속 전송한다. 프록시는 이를 parsed_updated 단일 이벤트로 변환해야 한다.
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse([
        { type: "stage", stage: "parsing" },
        {
          type: "result",
          data: {
            parsed: { description: "반도체 위주 PBR 전략", universe: ["KOSPI", "KOSDAQ"] },
            backtest_request: { strategy_id: "h1", symbols: ["005930"], symbol_count: 1 },
            symbol_count: 1,
          },
        },
        {
          type: "result_update",
          data: {
            parsed: {
              description: "반도체 위주 PBR 전략",
              universe: ["KOSPI", "KOSDAQ"],
              sector: "반도체",
            },
            backtest_request: { strategy_id: "h2", symbols: ["005930", "000660"], symbol_count: 2 },
            symbol_count: 2,
          },
        },
        "[DONE]",
      ])
    );

    const response = await POST(makeRequest({ prompt: "반도체 위주 PBR 전략", backend: "ollama" }));
    const events = await readEvents(response);
    const parsedEvents = events
      .map((e) => {
        try {
          return JSON.parse(e);
        } catch {
          return null;
        }
      })
      .filter(Boolean);

    const updated = parsedEvents.find((e) => e.type === "parsed_updated");
    expect(updated).toMatchObject({
      parsed: { sector: "반도체" },
      backtest_request: { strategy_id: "h2" },
      symbol_count: 2,
    });
    // 순서: parsed_final/dsl_ready(즉답) 이후에 parsed_updated가 온다.
    const order = parsedEvents.map((e) => e.type);
    expect(order.indexOf("parsed_updated")).toBeGreaterThan(order.indexOf("dsl_ready"));
  });

  it("parsed_final은 테마 되묻기 우선순위 마커(clarification_priority)를 보존한다", async () => {
    // 프록시 화이트리스트에서 이 필드가 빠지면 프론트의 theme_universe 우선 게이트가
    // 되묻기를 인식하지 못해 explicit 설정 질문(시장)이 덮어쓴다 — 'bts 관련 종목'이
    // 업종 전체로 강등되던 실측 사고(2026-07-25). FR-STR-071 ⑤ 우선순위 계약의 프록시 구간.
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: { description: "bts 관련 종목 투자 전략", universe: ["KOSPI", "KOSDAQ"] },
          backtest_request: { strategy_id: "h", symbols: ["352820"], symbol_count: 1 },
          clarification_question: "이 종목들로만 백테스트할까요, 아니면 업종 전체로 할까요?",
          clarification_suggestions: ["이 종목들로만 백테스트", "업종 전체로 백테스트"],
          clarification_priority: "theme_universe",
        })
      )
    );

    const response = await POST(makeRequest({ prompt: "bts 관련 종목 투자 전략" }));
    const events = await readEvents(response);
    const parsedFinal = events
      .map((e) => (e === "[DONE]" ? null : JSON.parse(e)))
      .find((e) => e?.type === "parsed_final");
    expect(parsedFinal).toMatchObject({
      clarification_priority: "theme_universe",
      clarification_question: "이 종목들로만 백테스트할까요, 아니면 업종 전체로 할까요?",
    });
  });

  it("parsed_final은 planner ask 컨텍스트(pending_ask)를 보존한다", async () => {
    // 프록시 화이트리스트에서 이 필드가 빠지면 프론트가 다음 파스 요청에 에코할 컨텍스트가
    // 사라져 칩 클릭의 결정론 귀속(run_chip_answer)이 조용히 죽는다 — priority 마커 누락
    // 사고(위 테스트)와 같은 유형의 함정. Phase 4 후속 ① 계약의 프록시 구간.
    const pendingAsk = {
      topic: "리스크관리",
      question: "손절·익절 기준을 정할까요?",
      chips: ["손절 8%", "익절 20%"],
    };
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: { description: "반도체 etf 전략", universe: ["ETF"] },
          backtest_request: { strategy_id: "p", symbols: ["069500"], symbol_count: 1 },
          clarification_question: "손절·익절 기준을 정할까요?",
          clarification_suggestions: ["손절 8%", "익절 20%"],
          clarification_priority: "dag_planner",
          pending_ask: pendingAsk,
        })
      )
    );

    const response = await POST(makeRequest({ prompt: "반도체 etf 전략" }));
    const events = await readEvents(response);
    const parsedFinal = events
      .map((e) => (e === "[DONE]" ? null : JSON.parse(e)))
      .find((e) => e?.type === "parsed_final");
    expect(parsedFinal).toMatchObject({ pending_ask: pendingAsk });
  });

  it("parsed_final은 값-대기 조건(pending_conditions)을 보존한다", async () => {
    // [회귀 2026-08-03 '당기순이익' 사고 2차] 백엔드는 pending_conditions를 실어 보냈는데
    // 프록시 화이트리스트에서 떨어져, 이해한 조건이 요약에 빈 전략으로 보였다 —
    // priority 마커·pending_ask 누락 사고와 같은 유형의 함정.
    const pendingConditions = [
      { role: "entry", label: "순이익증가율", source_text: "당기순이익과" },
      { role: "entry", label: "영업이익률", source_text: "영업이익률이 높은" },
    ];
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: { description: "당기순이익과 영업이익률이 높은 종목", universe: ["KOSPI200"] },
          backtest_request: { strategy_id: "p", symbols: ["005930"], symbol_count: 1 },
          clarification_question: "진입 조건의 영업이익률 기준값을 얼마로 할까요?",
          pending_conditions: pendingConditions,
        })
      )
    );

    const response = await POST(makeRequest({ prompt: "당기순이익과 영업이익률이 높은 종목" }));
    const events = await readEvents(response);
    const parsedFinal = events
      .map((e) => (e === "[DONE]" ? null : JSON.parse(e)))
      .find((e) => e?.type === "parsed_final");
    expect(parsedFinal).toMatchObject({ pending_conditions: pendingConditions });
  });

  it("forwards backend parse errors as SSE error events", async () => {
    fetchBackend.mockResolvedValueOnce({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ detail: "parse failed" }),
    });

    const response = await POST(makeRequest({ prompt: "bad prompt", backend: "mlx" }));
    const events = await readEvents(response);

    expect(JSON.parse(events[0])).toEqual({ type: "accepted" });
    expect(JSON.parse(events[2])).toEqual({ type: "error", detail: "parse failed" });
    expect(events[3]).toBe("[DONE]");
  });

  // 회귀(2026-08-07): 파스 한 턴은 LLM 3회로 800~1,000토큰을 생성하므로 소요 시간이
  // 머신의 그 시각 생성 처리량에 정비례한다(실측 11 tok/s→65초, 4 tok/s→300초).
  // 120초 예산에서는 파싱이 끝났는데도 프록시가 먼저 끊어 사용자에게
  // "aborted due to timeout"이 나갔다 — 예산을 줄이면 그 사고가 그대로 재발한다.
  it("gives the backend parse a budget wide enough for low-throughput turns", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(backendResultEvents({ parsed: {}, backtest_request: {} }))
    );

    await POST(makeRequest({ prompt: "코스피200 모멘텀 상위 12종목" }));

    const [, init] = fetchBackend.mock.calls[0];
    expect(init.timeoutMs).toBeGreaterThanOrEqual(240_000);
  });

  // '대화 종료' — 클라이언트가 스트림을 끊으면 백엔드 연결(fetchBackend signal)도 끊어야
  // 백엔드가 진행 중인 LLM 작업을 멈춘다. 프록시가 이를 전파하지 않으면 사용자는 끊었는데
  // 서버는 예산(240초)이 다할 때까지 파싱을 계속한다.
  it("aborts the backend fetch when the client disconnects (request signal)", async () => {
    let upstreamSignal: AbortSignal | undefined;
    const encoder = new TextEncoder();
    fetchBackend.mockImplementationOnce((_path: string, init: { signal?: AbortSignal }) => {
      upstreamSignal = init.signal;
      // 백엔드가 아직 결과를 내지 않은 채 열려 있는 SSE 스트림
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "stage", stage: "parsing" })}\n\n`));
        },
      });
      return Promise.resolve({ ok: true, body });
    });

    // Next는 클라이언트가 연결을 끊으면 req.signal을 abort한다 — 그 signal을 흉내낸다
    // (테스트 환경의 AbortSignal 렐름이 Request 생성자와 달라 RequestInit로는 못 넘긴다).
    const clientAbort = new AbortController();
    const request = makeRequest({ prompt: "코스피200 모멘텀 상위 12종목" });
    Object.defineProperty(request, "signal", { value: clientAbort.signal });
    const response = await POST(request);
    const reader = response.body!.getReader();
    await reader.read(); // accepted — 프록시가 백엔드 호출을 시작했다
    await vi.waitFor(() => expect(upstreamSignal).toBeInstanceOf(AbortSignal));
    expect(upstreamSignal!.aborted).toBe(false);

    clientAbort.abort();

    expect(upstreamSignal!.aborted).toBe(true);
  });

  it("aborts the backend fetch when the response stream is cancelled", async () => {
    let upstreamSignal: AbortSignal | undefined;
    fetchBackend.mockImplementationOnce((_path: string, init: { signal?: AbortSignal }) => {
      upstreamSignal = init.signal;
      return Promise.resolve({ ok: true, body: new ReadableStream<Uint8Array>({ start() {} }) });
    });

    const response = await POST(makeRequest({ prompt: "코스피200 모멘텀 상위 12종목" }));
    const reader = response.body!.getReader();
    await reader.read();
    await vi.waitFor(() => expect(upstreamSignal).toBeInstanceOf(AbortSignal));

    await reader.cancel();

    expect(upstreamSignal!.aborted).toBe(true);
  });

  it("returns 400 for invalid JSON", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/parse/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{",
        })
      )
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ detail: "Invalid JSON" });
    expect(fetchBackend).not.toHaveBeenCalled();
  });
});
