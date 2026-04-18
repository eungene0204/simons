import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";
import { computeCacheKey, findCachedResult, saveCachedResult } from "@/lib/server/backtestCache";

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

  // ── 캐시 조회: 동일 전략이면 즉시 반환 ──
  const cacheKey = computeCacheKey(body);
  const cached = await findCachedResult(cacheKey);

  if (cached) {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode(sseEvent({ type: "status", message: "캐시에서 결과를 불러옵니다..." })));
        controller.enqueue(encoder.encode(sseEvent({ type: "result", data: cached })));
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });

    return new NextResponse(stream, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  }

  // ── 캐시 미스: Python 백엔드로 프록시 + 결과 저장 ──
  try {
    const res = await fetchBackend("/strategy/backtest-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      timeoutMs: 600_000,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    // SSE 스트림을 클라이언트에 전달하면서 result 이벤트를 캡처해 DB에 저장
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let resultData: any = null;
    let sseBuffer = ""; // 청크 경계에서 잘린 라인을 버퍼링

    const stream = new ReadableStream({
      async pull(controller) {
        const { done, value } = await reader.read();
        if (done) {
          // 스트림 종료 후 결과 저장
          if (resultData) {
            saveCachedResult(cacheKey, body, resultData).catch(console.error);
          }
          controller.close();
          return;
        }

        // 원본 청크를 그대로 클라이언트에 전달
        controller.enqueue(value);

        // result 이벤트 캡처 — 라인 버퍼링으로 청크 분할 대응
        sseBuffer += decoder.decode(value, { stream: true });
        const lines = sseBuffer.split("\n");
        sseBuffer = lines.pop()!; // 마지막 불완전 라인은 버퍼에 유지

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          try {
            const event = JSON.parse(payload);
            if (event.type === "result" && event.data) {
              resultData = event.data;
            }
          } catch {
            // JSON 파싱 실패는 무시
          }
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
    return NextResponse.json(
      { detail: `Strategy backtest stream proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
