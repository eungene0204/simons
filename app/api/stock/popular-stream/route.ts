import { fetchBackend } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

const POPULAR_SYMBOLS = ["005930", "000660", "373220", "005380", "068270"];

export async function GET() {
  try {
    const res = await fetchBackend(
      `/market/prices-stream?symbols=${POPULAR_SYMBOLS.join(",")}`,
      {
        method: "GET",
        cache: "no-store",
        timeoutMs: 600_000,
        headers: { Accept: "text/event-stream" },
      }
    );

    if (!res.ok) {
      return new Response(`data: ${JSON.stringify({ error: "backend unavailable" })}\n\n`, {
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      });
    }

    return new Response(res.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return new Response(`data: ${JSON.stringify({ error: "stream error" })}\n\n`, {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    });
  }
}
