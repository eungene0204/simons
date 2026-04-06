import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export async function GET() {
  try {
    const res = await fetchBackend("/model/status", {
      cache: "no-store",
      timeoutMs: 30_000,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { error: `Model status proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
