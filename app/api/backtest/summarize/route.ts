import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";
import { prisma } from "@/lib/prisma";
import {
  deleteSummaryInFlight,
  getSummaryInFlight,
  getSummaryMemoryCache,
  rememberSummary,
  setSummaryInFlight,
  type SummaryCachePayload,
} from "./cache";

type SummaryPayload = {
  score: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  cached: boolean;
};

class SummarizeBackendError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }

  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}

async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function summaryPayloadKey(metrics: unknown, strategySummary: unknown): Promise<string> {
  return sha256(stableStringify({ metrics, strategySummary }));
}

async function fetchSummary(
  metrics: unknown,
  strategySummary: unknown
): Promise<SummaryCachePayload> {
  const res = await fetchBackend("/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metrics, strategySummary }),
    cache: "no-store",
    timeoutMs: 120_000,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new SummarizeBackendError(errData.detail ?? "Summarize failed", res.status);
  }

  const result = await res.json();
  return {
    score: result.score,
    summary: result.summary,
    strengths: result.strengths ?? [],
    weaknesses: result.weaknesses ?? [],
    improvements: result.improvements ?? [],
  };
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { metrics, strategySummary, cacheKey } = body;

    if (!metrics) {
      return NextResponse.json({ error: "Missing metrics" }, { status: 400 });
    }

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      const existingMetrics = existing?.metrics ? JSON.parse(existing.metrics) : null;

      if (existingMetrics?.aiSummary && existingMetrics?.aiScore != null) {
        return NextResponse.json({
          score: existingMetrics.aiScore,
          summary: existingMetrics.aiSummary,
          strengths: existingMetrics.aiStrengths ?? [],
          weaknesses: existingMetrics.aiWeaknesses ?? [],
          improvements: existingMetrics.aiImprovements ?? [],
          cached: true,
        });
      }
    }

    const payloadKey = await summaryPayloadKey(metrics, strategySummary);
    const memoryHit = getSummaryMemoryCache(payloadKey);
    if (memoryHit) {
      return NextResponse.json({ ...memoryHit, cached: true });
    }

    let pending = getSummaryInFlight(payloadKey);
    if (!pending) {
      pending = fetchSummary(metrics, strategySummary).finally(() => {
        deleteSummaryInFlight(payloadKey);
      });
      setSummaryInFlight(payloadKey, pending);
    }

    const generated = await pending;
    rememberSummary(payloadKey, generated);

    const payload: SummaryPayload = {
      ...generated,
      cached: false,
    };

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      if (existing) {
        const currentMetrics = existing.metrics ? JSON.parse(existing.metrics) : {};
        await prisma.backtestHistory.update({
          where: { cacheKey },
          data: {
            metrics: JSON.stringify({
              ...currentMetrics,
              aiSummary: payload.summary ?? currentMetrics.aiSummary,
              aiScore: payload.score ?? currentMetrics.aiScore,
              aiStrengths: payload.strengths,
              aiWeaknesses: payload.weaknesses,
              aiImprovements: payload.improvements,
            }),
          },
        });
      }
    }

    return NextResponse.json({
      ...payload,
    });
  } catch (error: any) {
    if (error instanceof SummarizeBackendError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }

    console.error("Summarize error:", error);
    return NextResponse.json(
      { error: `Summarize proxy error: ${error?.message ?? "Internal server error"}` },
      { status: 500 }
    );
  }
}
