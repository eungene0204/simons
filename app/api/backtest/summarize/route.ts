import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { metrics, strategySummary } = body;

    if (!metrics) {
      return NextResponse.json({ error: "Missing metrics" }, { status: 400 });
    }

    const res = await fetch("http://localhost:8000/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metrics, strategySummary }),
      cache: "no-store",
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
      return NextResponse.json(
        { error: errData.detail ?? "Summarize failed" },
        { status: res.status }
      );
    }

    const result = await res.json();
    return NextResponse.json({
      score: result.score,
      summary: result.summary,
      strengths: result.strengths ?? [],
      risks: result.risks ?? [],
    });
  } catch (error: any) {
    console.error("Summarize error:", error);
    return NextResponse.json(
      { error: error?.message ?? "Internal server error" },
      { status: 500 }
    );
  }
}
