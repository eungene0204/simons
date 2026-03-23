import { NextResponse } from "next/server";
import { exec } from "child_process";
import util from "util";

const execPromise = util.promisify(exec);

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { metrics, strategySummary } = body;

    if (!metrics) {
      return NextResponse.json({ error: "Missing metrics" }, { status: 400 });
    }

    const payload = JSON.stringify({ metrics, strategySummary });
    // Escape single quotes in payload for shell safety
    const escapedPayload = payload.replace(/'/g, "'\\''");

    const command = `PYTHONPATH=.:backend python backend/ai/summarize.py '${escapedPayload}'`;
    const { stdout, stderr } = await execPromise(command, { timeout: 120_000 });

    try {
      const result = JSON.parse(stdout.trim());
      if (result.error) {
        return NextResponse.json({ error: result.error }, { status: 500 });
      }
      return NextResponse.json({ summary: result.summary });
    } catch {
      console.error("Failed to parse summarize output:", stdout);
      console.error("stderr:", stderr);
      return NextResponse.json({ error: "Failed to parse output" }, { status: 500 });
    }
  } catch (error: any) {
    if (error?.signal === "SIGTERM" || error?.killed) {
      return NextResponse.json({ error: "요약 생성 시간 초과" }, { status: 504 });
    }
    console.error("Summarize error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
