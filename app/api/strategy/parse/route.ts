import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export async function POST(req: NextRequest) {
  let body: unknown;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  try {
    const res = await fetchBackend("/strategy/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      timeoutMs: 120_000,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Strategy parse proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
