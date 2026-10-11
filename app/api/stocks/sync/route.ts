// @ts-nocheck
import { NextRequest, NextResponse } from "next/server";
import { loadStockList, StockListItem } from "@/lib/krx-stocks";
import { requireAdmin } from "@/lib/server/adminAuth";
import { internalTokenHeader } from "@/lib/server/backend";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/**
 * 코스피/코스닥 종목 목록을 동기화하는 API.
 *
 * Python 백엔드의 /sync-stocks endpoint를 호출한다.
 * 백엔드는 FinanceDataReader(FDR)로 KRX 공식 데이터를 가져와
 * 검증 후 korea-stocks.json에 저장한다.
 *
 * ⚠️  이전에 사용하던 krx-stocks.ts의 fetchKRXStockList()는
 *      KRX 비공식 통계 API를 직접 호출해 이름-코드 매핑이 잘못되는
 *      문제가 있었으므로 더 이상 사용하지 않는다.
 */
export async function POST(_request: NextRequest) {
  // 전체 종목 명부를 다시 쓰는 운영 작업이다 — 화면에서 부르는 곳이 없는 수동 엔드포인트인데
  // 권한 확인 없이 열려 있었다(2026-10-11 보안 점검). 관리자만, 비관리자에게는 존재를 숨긴다.
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "Not Found" }, { status: 404 });
  try {
    const backendRes = await fetch(`${BACKEND_URL}/sync-stocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...internalTokenHeader() },
    });

    if (!backendRes.ok) {
      const err = await backendRes.text();
      return NextResponse.json(
        { error: "Backend sync-stocks 실패", detail: err },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();

    if (data.validation_warnings?.length) {
      console.warn("[sync-stocks] validation warnings:", data.validation_warnings);
    }

    return NextResponse.json({
      success: true,
      count: data.count,
      kospi: data.kospi,
      kosdaq: data.kosdaq,
      added: data.added ?? 0,
      delisted: data.delisted ?? 0,
      added_symbols: data.added_symbols ?? [],
      delisted_symbols: data.delisted_symbols ?? [],
      date: data.date ?? null,
      validation_warnings: data.validation_warnings ?? [],
      message: `${data.count}개 종목 저장 완료 (KOSPI ${data.kospi}, KOSDAQ ${data.kosdaq}, 신규 ${data.added ?? 0}, 상폐 ${data.delisted ?? 0})`,
    });
  } catch (error) {
    console.error("Failed to sync stock list:", error);
    return NextResponse.json(
      {
        error: "종목 목록 동기화 실패 — 백엔드 서버가 실행 중인지 확인하세요",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}

/**
 * 저장된 종목 목록을 조회하는 API
 */
export async function GET(request: NextRequest) {
  try {
    const stocks = await loadStockList();

    const searchParams = request.nextUrl.searchParams;
    const market = searchParams.get("market");
    const query = searchParams.get("q");

    let filteredStocks: StockListItem[] = stocks;

    if (market) {
      filteredStocks = filteredStocks.filter(
        (stock) => stock.market === market.toUpperCase()
      );
    }

    if (query) {
      const lowerQuery = query.toLowerCase();
      filteredStocks = filteredStocks.filter(
        (stock) =>
          stock.symbol.includes(query) ||
          stock.name.toLowerCase().includes(lowerQuery)
      );
    }

    return NextResponse.json({
      success: true,
      count: filteredStocks.length,
      stocks: filteredStocks,
    });
  } catch (error) {
    console.error("Failed to load stock list:", error);
    return NextResponse.json(
      {
        error: "종목 목록 조회 실패",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
