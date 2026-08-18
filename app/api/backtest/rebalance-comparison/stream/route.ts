import { NextRequest } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

// 리밸런싱 기간별 결과 비교(FR-BT-064) SSE 프록시 — 백엔드의 주기 단위 진행률·결과 이벤트를
// 그대로 전달한다. fetchBackend를 쓰는 이유는 UI 언어 헤더(X-UI-Language)를 실어 LLM 서술
// 언어를 맞추기 위해서다. 클라이언트가 취소(req.signal)하면 백엔드 연결도 끊겨 다음 주기
// 경계에서 협조적으로 중단된다.
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    // 백엔드 자체 제한(REBALANCE_COMPARISON_TIMEOUT_S, 기본 3600초)이 친절한 SSE 에러를 내보내므로
    // 프록시 안전망은 반드시 그보다 커야 한다(같거나 작으면 사용자는 "연결 끊김"만 본다).
    const res = await fetchBackend("/rebalance-comparison/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: req.signal,
      timeoutMs: 3_660_000,
    });

    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return Response.json(err, { status: res.status });
    }

    // undici 응답 본문을 그대로 넘기지 않고 읽어서 흘려보낸다(다른 SSE 프록시와 같은 방식 —
    // 런타임별 ReadableStream 구현 차이를 피한다).
    const reader = res.body.getReader();
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { done, value } = await reader.read();
        if (done) {
          controller.close();
          return;
        }
        controller.enqueue(value);
      },
      cancel() {
        reader.cancel().catch(() => {});
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (e: any) {
    return Response.json(
      { detail: `Rebalance comparison stream proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
