import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export interface BatchQuoteItem {
  price: number;
  changePercent: number;
  volume: number;
}

// POST body: { symbols: string[] }
// Response: { [symbol]: BatchQuoteItem }
export async function POST(request: NextRequest) {
  const { symbols }: { symbols: string[] } = await request.json();

  if (!Array.isArray(symbols) || symbols.length === 0) {
    return NextResponse.json({});
  }

  const zero = (sym: string): [string, BatchQuoteItem] => [
    sym,
    { price: 0, changePercent: 0, volume: 0 },
  ];

  try {
    const res = await fetch(`${BACKEND_URL}/market/prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(Object.fromEntries(symbols.map(zero)));
    }

    const data: Record<string, { close: number; open: number; volume: number; prev_close?: number; change_rate?: number }> =
      await res.json();

    const result: Record<string, BatchQuoteItem> = {};
    for (const sym of symbols) {
      const q = data[sym];
      if (q?.close) {
        // provider가 제공한 등락률 우선, 없으면 prev_close 기반 계산, 그것도 없으면 시가 기반
        let changePercent: number;
        if (q.change_rate !== undefined && q.change_rate !== 0) {
          changePercent = q.change_rate;
        } else {
          const base = q.prev_close && q.prev_close > 0 ? q.prev_close : q.open;
          changePercent = base > 0 ? Math.round(((q.close - base) / base) * 10000) / 100 : 0;
        }
        result[sym] = {
          price: q.close,
          changePercent,
          volume: q.volume ?? 0,
        };
      } else {
        result[sym] = { price: 0, changePercent: 0, volume: 0 };
      }
    }
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(Object.fromEntries(symbols.map(zero)));
  }
}
