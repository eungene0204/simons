import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";
import { computeCacheKey, saveCachedResult, resolveStrategyId } from "@/lib/server/backtestCache";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import {
  consumeBacktestQuota,
  PLAN_LIMIT_BACKTESTS,
  PLAN_LIMIT_MESSAGES,
} from "@/lib/server/planLimits";

function makeTraceId(): string {
  return `bt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function summarizeBacktestResult(result: any) {
  return {
    totalReturn: result?.totalReturn ?? null,
    cagr: result?.cagr ?? null,
    trades: result?.trades ?? null,
    warnings: Array.isArray(result?.warnings) ? result.warnings.length : 0,
    signals: Array.isArray(result?.signals) ? result.signals.length : 0,
    fromCache: result?.fromCache ?? false,
  };
}

function sseEvent(data: object | string): string {
  const payload = typeof data === "string" ? data : JSON.stringify(data);
  return `data: ${payload}\n\n`;
}

export async function POST(req: NextRequest) {
  let body: any;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  // 로그인 사용자는 월 백테스트 한도를 검사하고 1회 소비한다(캐시 히트도 실행 1회로 집계).
  // 프론트는 !res.ok 시 err.detail을 에러 메시지로 표시하므로 429에 detail을 포함한다.
  const user = await getCurrentUser();
  if (user) {
    try {
      await consumeBacktestQuota(prisma, user.id);
    } catch (err: any) {
      if (err instanceof Error && err.message === PLAN_LIMIT_BACKTESTS) {
        return NextResponse.json(
          {
            error: "Backtest limit reached",
            code: PLAN_LIMIT_BACKTESTS,
            detail: PLAN_LIMIT_MESSAGES[PLAN_LIMIT_BACKTESTS],
            message: PLAN_LIMIT_MESSAGES[PLAN_LIMIT_BACKTESTS],
          },
          { status: 429 }
        );
      }
      throw err;
    }
  }

  // 캐시 히트 여부와 무관하게 항상 엔진을 새로 실행한다(같은 전략이라도 재실행 정책).
  // cacheKey는 결과 저장(dedup 업서트) 및 클라이언트 표시용으로만 사용한다.
  const strategyId = resolveStrategyId(body);
  const cacheKey = computeCacheKey(body);
  const traceId = makeTraceId();
  const log = (step: string, meta: Record<string, unknown> = {}) => {
    console.log(`[BT-STREAM:${traceId}] ${step}`, {
      cacheKey,
      strategyId,
      ...meta,
    });
  };

  log("request_received", {
    symbols: Array.isArray(body?.symbols) ? body.symbols.length : 0,
    period: body?.period ?? body?.backtest_period ?? null,
    startDate: body?.startDate ?? body?.start_date ?? null,
    endDate: body?.endDate ?? body?.end_date ?? null,
  });

  // ── Python 백엔드로 프록시 + 결과 저장 ──
  try {
    log("python_backend_request_start", { path: "/strategy/backtest-stream" });
    const res = await fetchBackend("/strategy/backtest-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      timeoutMs: 600_000,
    });
    log("python_backend_response", { ok: res.ok, status: res.status });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      log("python_backend_error_response", { status: res.status, detail: err?.detail ?? null });
      return NextResponse.json(err, { status: res.status });
    }

    // SSE 스트림을 클라이언트에 전달하면서 result 이벤트를 캡처해 DB에 저장
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let resultData: any = null;
    let sseBuffer = ""; // 청크 경계에서 잘린 라인을 버퍼링
    log("sse_proxy_opened");

    const stream = new ReadableStream({
      start(controller) {
        // 결과 dedup 키를 Python 결과 청크보다 먼저 전달한다.
        controller.enqueue(
          new TextEncoder().encode(sseEvent({ type: "meta", cacheKey }))
        );
      },
      async pull(controller) {
        const processBlock = (block: string) => {
          const dataLines = block
            .split(/\r?\n/)
            .filter((line) => line.startsWith("data: "))
            .map((line) => line.slice(6).trim());

          for (const payload of dataLines) {
            if (payload === "[DONE]") {
              log("python_done_received");
              log("sse_done_sent", { source: "python", mode: "passthrough" });
              continue;
            }

            try {
              const event = JSON.parse(payload);
              if (event.type === "status") {
                log("python_status_received", { message: event.message ?? null });
              }
              if (event.type === "result" && event.data) {
                resultData = {
                  ...event.data,
                  strategy_id: event.data.strategy_id ?? strategyId ?? cacheKey,
                };
                log("python_result_received", summarizeBacktestResult(resultData));
              }
              if (event.type === "error") {
                log("python_error_event_received", { message: event.message ?? null });
              }
            } catch {
              // JSON 파싱 실패는 무시
            }
          }
        };

        const processBufferedBlocks = (buffer: string) => {
          const blocks = buffer.split(/\r?\n\r?\n/);
          for (const block of blocks) {
            if (block.trim()) processBlock(block.trimEnd());
          }
        };

        const { done, value } = await reader.read();
        if (done) {
          const remaining = `${sseBuffer}${decoder.decode()}`;
          if (remaining.trim()) {
            processBufferedBlocks(remaining);
            sseBuffer = "";
          }
          log("stream_closed", { source: "python" });
          if (resultData) {
            log("cache_save_started", summarizeBacktestResult(resultData));
            try {
              // Keep the request alive until Strategy.settings and BacktestHistory.strategyId
              // are persisted. Fire-and-forget work can be terminated after the stream closes.
              await saveCachedResult(cacheKey, body, resultData, { throwOnFailure: true });
              log("cache_save_done");
            } catch (err: any) {
              log("cache_save_failed", { message: err?.message ?? String(err) });
            }
          }
          controller.close();
          return;
        }

        // 원본 SSE 청크는 절대 재조립하지 않고 즉시 클라이언트로 전달한다.
        // 로그/캐시 캡처는 아래 디코딩된 복사본만 사용한다.
        controller.enqueue(value);

        // result 이벤트 캡처 — 라인 버퍼링으로 청크 분할 대응
        sseBuffer += decoder.decode(value, { stream: true });
        const blocks = sseBuffer.split(/\r?\n\r?\n/);
        sseBuffer = blocks.pop()!; // 마지막 불완전 블록은 버퍼에 유지

        for (const block of blocks) {
          if (block.trim()) processBlock(block);
        }
      },
    });

    return new NextResponse(stream, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") || "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (e: any) {
    log("route_error", { message: e.message });
    return NextResponse.json(
      { detail: `Strategy backtest stream proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
