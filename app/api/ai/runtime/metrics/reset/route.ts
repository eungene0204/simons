import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export async function POST() {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { error: "AI runtime metrics reset is disabled in production" },
      { status: 403 }
    );
  }

  try {
    const res = await fetchBackend("/ai/runtime/metrics/reset", {
      method: "POST",
      cache: "no-store",
      timeoutMs: 30_000,
    });

    const data = await res.json().catch(() => ({ detail: res.statusText }));
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: `AI runtime metrics reset proxy error: ${error.message}` },
      { status: 500 }
    );
  }
}
