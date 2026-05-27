import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const [delistRes, noticesRes] = await Promise.all([
      fetch(`${BACKEND_URL}/market/delist`, { next: { revalidate: 300 } }),
      fetch(`${BACKEND_URL}/market/dart/notices?days=30`, { next: { revalidate: 300 } }),
    ]);

    const delisted: string[] = delistRes.ok
      ? (await delistRes.json()).delisted ?? []
      : [];

    const warningSymbols = new Set<string>();
    if (noticesRes.ok) {
      const { notices } = await noticesRes.json();
      for (const n of notices ?? []) {
        if (n.stock_code && !delisted.includes(n.stock_code)) {
          warningSymbols.add(n.stock_code);
        }
      }
    }

    return NextResponse.json({
      delisted,
      warning: Array.from(warningSymbols),
    });
  } catch {
    return NextResponse.json({ delisted: [], warning: [] });
  }
}
