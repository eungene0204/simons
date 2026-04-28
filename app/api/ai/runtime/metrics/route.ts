import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export async function GET() {
  try {
    const res = await fetchBackend("/ai/runtime/metrics", {
      cache: "no-store",
      timeoutMs: 30_000,
    });

    const data = await res.json().catch(() => ({ detail: res.statusText }));
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: `AI runtime metrics proxy error: ${error.message}` },
      { status: 500 }
    );
  }
}
