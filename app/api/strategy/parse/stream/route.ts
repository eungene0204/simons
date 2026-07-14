import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

type ParseStreamBody = {
  prompt?: string;
  backend?: string;
  model?: string;
  previous_parsed?: Record<string, unknown>;
};

function sseEvent(data: object | string): string {
  const payload = typeof data === "string" ? data : JSON.stringify(data);
  return `data: ${payload}\n\n`;
}

function compactPrompt(prompt: string): string {
  return prompt.toLowerCase().replace(/\s+/g, "");
}

function previousUniverse(body: ParseStreamBody): string[] | null {
  const universe = body.previous_parsed?.universe;
  if (!Array.isArray(universe)) return null;
  const normalized = universe.filter((item): item is string => typeof item === "string" && item.length > 0);
  return normalized.length > 0 ? normalized : null;
}

function inferUniverse(prompt: string, body?: ParseStreamBody): string[] {
  const compact = compactPrompt(prompt);
  if (compact.includes("코스피200") || compact.includes("kospi200")) return ["KOSPI200"];
  if (
    compact.includes("전체시장") ||
    compact.includes("코스피+코스닥") ||
    compact.includes("kospi+kosdaq")
  ) {
    return ["KOSPI", "KOSDAQ"];
  }
  if (compact.includes("코스닥") || compact.includes("kosdaq")) return ["KOSDAQ"];
  if (compact.includes("코스피") || compact.includes("kospi")) return ["KOSPI"];
  const inherited = body ? previousUniverse(body) : null;
  if (inherited) return inherited;
  return ["KOSPI200"];
}

function inferMaxPositions(prompt: string): number | null {
  const match = compactPrompt(prompt).match(/(?:최대|상위)?(\d+)(?:개|종목)/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(100, parsed)) : null;
}

function inferRecognizedTerms(prompt: string): string[] {
  const compact = compactPrompt(prompt);
  const terms: Array<[string, string[]]> = [
    ["pbr", ["pbr"]],
    ["per", ["per"]],
    ["roe", ["roe", "gpa"]],
    ["ma_crossover", ["골든크로스", "데드크로스", "이동평균", "이평선"]],
    ["rsi", ["rsi"]],
    ["macd", ["macd"]],
    ["bollinger_bands", ["볼린저", "bollinger"]],
    ["breakout", ["신고가", "브레이크아웃", "breakout"]],
    ["stop_loss", ["손절", "손실", "하락"]],
    ["take_profit", ["익절", "수익"]],
    ["hold_period", ["보유", "리밸런싱"]],
  ];

  return terms
    .filter(([, keywords]) => keywords.some((keyword) => compact.includes(keyword)))
    .map(([term]) => term);
}

function buildSkeleton(body: ParseStreamBody) {
  const prompt = String(body.prompt ?? "");
  const recognizedTerms = inferRecognizedTerms(prompt);

  return {
    type: "skeleton",
    data: {
      description: prompt,
      universe: inferUniverse(prompt, body),
      max_positions: inferMaxPositions(prompt),
      recognized_terms: recognizedTerms,
      confidence: recognizedTerms.length > 0 ? "partial" : "low",
    },
  };
}

function streamHeaders() {
  return {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  };
}

export async function POST(req: NextRequest) {
  let body: ParseStreamBody;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();
      const send = (event: object | string) => {
        controller.enqueue(encoder.encode(sseEvent(event)));
      };

      send({ type: "accepted" });
      send(buildSkeleton(body));

      // 백엔드 parse-stream의 SSE 이벤트를 받아 클라이언트용 이벤트로 변환한다.
      // - stage: 그대로 전달(parsing→thinking 진행 표시)
      // - result: parsed_final + dsl_ready로 분해
      // - result_update: 후행 LLM 검증 교정 → parsed_updated 단일 이벤트로 전달
      // - error: detail 전달
      const handleEvent = (payload: string) => {
        if (payload === "[DONE]") return;
        let event: any;
        try {
          event = JSON.parse(payload);
        } catch {
          return;
        }
        if (event.type === "stage") {
          send({ type: "stage", stage: event.stage });
        } else if (event.type === "result") {
          const data = event.data ?? {};
          send({
            type: "parsed_final",
            parsed: data.parsed,
            clarification_question: data.clarification_question ?? null,
            clarification_suggestions: data.clarification_suggestions ?? null,
            risk_overrides: data.risk_overrides ?? null,
            notices: data.notices ?? null,
          });
          send({
            type: "dsl_ready",
            backtest_request: data.backtest_request,
            symbol_count: data.symbol_count ?? data.backtest_request?.symbol_count ?? null,
          });
        } else if (event.type === "result_update") {
          // 룰 파스 결과를 먼저 보낸 뒤 도착한 검증 교정본. 클라이언트가 실행 전이면
          // 전략·백테스트 요청을 조용히 갱신한다(로딩 표시로 되돌아가지 않음).
          const data = event.data ?? {};
          send({
            type: "parsed_updated",
            parsed: data.parsed,
            backtest_request: data.backtest_request,
            symbol_count: data.symbol_count ?? null,
            risk_overrides: data.risk_overrides ?? null,
            notices: data.notices ?? null,
          });
        } else if (event.type === "error") {
          send({ type: "error", detail: event.detail ?? "파싱 실패" });
        }
      };

      const processBlocks = (blocks: string[]) => {
        for (const block of blocks) {
          if (!block.trim()) continue;
          const line = block.split(/\r?\n/).find((l) => l.startsWith("data: "));
          if (line) handleEvent(line.slice(6).trim());
        }
      };

      try {
        const res = await fetchBackend("/strategy/parse-stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          cache: "no-store",
          timeoutMs: 120_000,
        });

        if (!res.ok || !res.body) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          send({ type: "error", detail: err.detail ?? res.statusText });
          send("[DONE]");
          controller.close();
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            buffer += decoder.decode();
            processBlocks(buffer.split(/\r?\n\r?\n/));
            buffer = "";
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\r?\n\r?\n/);
          buffer = blocks.pop() ?? "";
          processBlocks(blocks);
        }

        send("[DONE]");
        controller.close();
      } catch (error: any) {
        send({ type: "error", detail: `Strategy parse stream proxy error: ${error.message}` });
        send("[DONE]");
        controller.close();
      }
    },
  });

  return new NextResponse(stream, {
    status: 200,
    headers: streamHeaders(),
  });
}
