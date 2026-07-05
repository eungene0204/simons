import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

// 워크포워드 SSE 스트리밍 프록시 — 백엔드의 창 단위 진행률 이벤트를 그대로 전달한다.
// 클라이언트가 취소(req.signal)하면 백엔드 연결도 끊겨 다음 창 경계에서 협조적으로 중단된다.
export async function POST(req: NextRequest) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 600_000);
  req.signal?.addEventListener("abort", () => controller.abort());

  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND_URL}/walk-forward/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      clearTimeout(timeoutId);
      return Response.json(err, { status: res.status });
    }

    // 스트림이 끝나면 타임아웃 타이머를 정리한다.
    const cleanupStream = res.body.pipeThrough(
      new TransformStream({
        flush() {
          clearTimeout(timeoutId);
        },
      })
    );

    return new Response(cleanupStream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (e: any) {
    clearTimeout(timeoutId);
    return Response.json(
      { detail: `Walk-forward stream proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
