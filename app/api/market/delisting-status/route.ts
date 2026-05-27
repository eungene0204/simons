import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

// GET /api/market/delisting-status?symbols=005930,000660,...
// 심볼 파라미터 있으면 해당 종목만, 없으면 비정상 상태 전체
// DB만 사용 — 외부 API 호출 없음 (listing status는 별도 동기화 작업으로 관리)
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbolsParam = searchParams.get('symbols');

  try {
    const dbStatuses = await prisma.stock.findMany({
      where: { listingStatus: { not: 'NORMAL' } },
      select: { symbol: true, name: true, listingStatus: true, lastTradableDate: true, delistingDate: true, suspensionReason: true },
    });

    const delisted: string[] = [];
    const warningSymbols = new Set<string>();
    const tradingSuspended = new Set<string>();
    const delistingScheduled = new Set<string>();
    const delistingReview = new Set<string>();
    const names: Record<string, string> = {};

    for (const s of dbStatuses) {
      if (s.name) names[s.symbol] = s.name;
      switch (s.listingStatus) {
        case 'DELISTED': delisted.push(s.symbol); break;
        case 'DELISTING_SCHEDULED': delistingScheduled.add(s.symbol); break;
        case 'TRADING_SUSPENDED': tradingSuspended.add(s.symbol); break;
        case 'DELISTING_REVIEW': delistingReview.add(s.symbol); break;
        case 'WARNING': case 'RISK': warningSymbols.add(s.symbol); break;
      }
    }

    // 심볼 필터 적용
    const filterSymbols = symbolsParam ? new Set(symbolsParam.split(',').map((s) => s.trim())) : null;
    const filter = (arr: string[]) =>
      filterSymbols ? arr.filter((s) => filterSymbols.has(s)) : arr;
    const filterSet = (s: Set<string>) =>
      filterSymbols ? Array.from(s).filter((x) => filterSymbols.has(x)) : Array.from(s);

    // 상세 정보 맵
    const detailMap: Record<string, {
      listingStatus: string;
      lastTradableDate: string | null;
      delistingDate: string | null;
      suspensionReason: string | null;
    }> = {};
    for (const s of dbStatuses) {
      detailMap[s.symbol] = {
        listingStatus: s.listingStatus,
        lastTradableDate: s.lastTradableDate,
        delistingDate: s.delistingDate,
        suspensionReason: s.suspensionReason,
      };
    }

    return NextResponse.json({
      delisted: filter(delisted),
      warning: filterSet(warningSymbols),
      tradingSuspended: filterSet(tradingSuspended),
      delistingScheduled: filterSet(delistingScheduled),
      delistingReview: filterSet(delistingReview),
      details: detailMap,
      names,
    });
  } catch {
    return NextResponse.json({
      delisted: [],
      warning: [],
      tradingSuspended: [],
      delistingScheduled: [],
      delistingReview: [],
      details: {},
    });
  }
}
