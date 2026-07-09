import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getStockNameMap } from "@/lib/krx-stocks";

// DELETE: 시그널 히스토리 전체 삭제
export async function DELETE(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    await prisma.virtualMarketLog.deleteMany({
      where: { accountId: params.accountId },
    });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Failed to delete market logs:", error);
    return NextResponse.json(
      { error: "Failed to delete logs" },
      { status: 500 }
    );
  }
}

// GET: 시그널/거래 로그 조회
export async function GET(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get("limit") || "50");

    const logs = await prisma.virtualMarketLog.findMany({
      where: { accountId: params.accountId },
      orderBy: { createdAt: "desc" },
      take: limit,
    });

    // 이름이 없거나 종목코드가 그대로 이름에 들어간 로그의 symbol만 추가 조회
    // (백엔드 자동매매가 Stock 테이블에서 이름을 못 찾으면 symbol을 stockName에 그대로 저장함)
    const hasResolvedName = (l: { stockName: string | null; symbol: string }) =>
      !!l.stockName && l.stockName !== l.symbol;
    const unknownSymbols = [...new Set(
      logs.filter((l) => !hasResolvedName(l)).map((l) => l.symbol)
    )];

    const [jsonNameMap, dbStocks] = await Promise.all([
      unknownSymbols.length > 0 ? getStockNameMap() : Promise.resolve({} as Record<string, string>),
      unknownSymbols.length > 0
        ? prisma.stock.findMany({
            where: { symbol: { in: unknownSymbols } },
            select: { symbol: true, name: true },
          })
        : Promise.resolve([]),
    ]);

    const dbNameMap: Record<string, string> = Object.fromEntries(
      dbStocks.filter((s) => s.name).map((s) => [s.symbol, s.name!])
    );

    const logsWithName = logs.map((log) => ({
      ...log,
      stockName: hasResolvedName(log)
        ? log.stockName
        : jsonNameMap[log.symbol] ?? dbNameMap[log.symbol] ?? null,
    }));

    return NextResponse.json(logsWithName);
  } catch (error) {
    console.error("Failed to get market logs:", error);
    return NextResponse.json(
      { error: "Failed to get logs" },
      { status: 500 }
    );
  }
}
