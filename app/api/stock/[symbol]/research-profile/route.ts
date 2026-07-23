import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 단일 종목 연구 프로파일(FR-STR-068b) — 종목 선택 직후 데이터 기간·가능 전략 유형·
// 노출/제외 질문과 이유를 조회한다(백엔드 결정론 StockProfileService 프록시).
export async function GET(
  req: NextRequest,
  { params }: { params: { symbol: string } },
) {
  const symbol = params.symbol
  if (!/^[0-9A-Z]{6}$/.test(symbol)) {
    return NextResponse.json({ detail: '유효한 종목 코드가 아닙니다.' }, { status: 404 })
  }
  const includeAdvanced = req.nextUrl.searchParams.get('include_advanced') === 'true'
  try {
    const res = await fetchBackend(
      `/stock/${symbol}/research-profile?include_advanced=${includeAdvanced}`,
      { method: 'GET', cache: 'no-store', timeoutMs: 30_000 },
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch (e: any) {
    return NextResponse.json({ detail: `Stock profile proxy error: ${e.message}` }, { status: 500 })
  }
}
