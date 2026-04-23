import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

// Seed news items shown when backend is unavailable (dev/test only)
const SEED_NEWS: Record<string, object[]> = {
  '005930': [
    {
      id: 'seed-001',
      title: '삼성전자, 2분기 영업이익 10조 돌파…반도체 업황 회복 본격화',
      summary: '삼성전자가 2분기 영업이익 10조 원을 넘기며 시장 예상치를 상회했다. 메모리 반도체 가격 반등과 HBM 수요 급증이 실적을 이끌었다.',
      url: 'https://example.com/news/001',
      source: '한국경제',
      published_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
      category: '기업',
      symbols: ['005930'],
      scope: 'stock',
      sector: '반도체',
      event_type: 'earnings_beat',
      sentiment: 'positive',
      severity: 0.82,
      credibility: 0.9,
      risk_flags: [],
      impact_direction: 'up',
      impact_score: 0.64,
      confidence_score: 0.78,
      expected_alpha_1d: 0.031,
    },
    {
      id: 'seed-002',
      title: '삼성전자, 1조 원 규모 자사주 매입 계획 발표',
      summary: '삼성전자는 주주가치 제고를 위해 보통주 1조 원, 우선주 1,000억 원 규모의 자사주 취득을 결정했다고 공시했다.',
      url: 'https://example.com/news/002',
      source: '연합뉴스',
      published_at: new Date(Date.now() - 5 * 3600 * 1000).toISOString(),
      category: '공시',
      symbols: ['005930'],
      scope: 'stock',
      sector: null,
      event_type: 'share_buyback',
      sentiment: 'positive',
      severity: 0.65,
      credibility: 0.95,
      risk_flags: [],
      impact_direction: 'up',
      impact_score: 0.45,
      confidence_score: 0.85,
      expected_alpha_1d: 0.018,
    },
    {
      id: 'seed-003',
      title: '삼성전자 목표주가 9만 원으로 상향…"HBM4 양산 기대"',
      summary: '메리츠증권은 삼성전자의 목표주가를 기존 8만 원에서 9만 원으로 상향 조정했다. HBM4 양산 일정이 앞당겨지면서 AI 반도체 수혜가 본격화될 것이라는 분석이다.',
      url: 'https://example.com/news/003',
      source: '매일경제',
      published_at: new Date(Date.now() - 8 * 3600 * 1000).toISOString(),
      category: '증권',
      symbols: ['005930'],
      scope: 'stock',
      sector: '반도체',
      event_type: 'analyst_upgrade',
      sentiment: 'positive',
      severity: 0.55,
      credibility: 0.8,
      risk_flags: [],
      impact_direction: 'up',
      impact_score: 0.38,
      confidence_score: 0.72,
      expected_alpha_1d: 0.012,
    },
    {
      id: 'seed-004',
      title: '삼성전자 파운드리 적자 지속…TSMC와 격차 확대 우려',
      summary: '삼성전자 파운드리 사업부가 3분기에도 수천억 원대 적자를 기록할 것으로 예상된다. 수율 문제와 고객사 이탈이 겹치며 TSMC와의 점유율 격차가 벌어지고 있다.',
      url: 'https://example.com/news/004',
      source: '조선비즈',
      published_at: new Date(Date.now() - 14 * 3600 * 1000).toISOString(),
      category: '기업',
      symbols: ['005930'],
      scope: 'stock',
      sector: '반도체',
      event_type: 'guidance_down',
      sentiment: 'negative',
      severity: 0.6,
      credibility: 0.75,
      risk_flags: [],
      impact_direction: 'down',
      impact_score: -0.42,
      confidence_score: 0.65,
      expected_alpha_1d: -0.015,
    },
    {
      id: 'seed-005',
      title: '삼성전자, 美 텍사스 반도체 공장 증설 투자 최종 확정',
      summary: '삼성전자가 미국 텍사스주 테일러 공장에 추가 투자를 확정했다. 미국 정부의 반도체법(CHIPS Act) 보조금 수령과 연계된 결정이다.',
      url: 'https://example.com/news/005',
      source: 'Naver Finance',
      published_at: new Date(Date.now() - 20 * 3600 * 1000).toISOString(),
      category: '기업',
      symbols: ['005930'],
      scope: 'stock',
      sector: '반도체',
      event_type: 'large_contract',
      sentiment: 'positive',
      severity: 0.7,
      credibility: 0.88,
      risk_flags: [],
      impact_direction: 'up',
      impact_score: 0.5,
      confidence_score: 0.76,
      expected_alpha_1d: 0.021,
    },
  ],
}

function getSeedItems(symbol: string, pageSize: number) {
  const items = SEED_NEWS[symbol] ?? []
  return {
    items: items.slice(0, pageSize),
    total: items.length,
    page: 1,
    page_size: pageSize,
    _source: 'seed',
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const { searchParams } = request.nextUrl
  const pageSize = parseInt(searchParams.get('page_size') ?? '20', 10)

  try {
    const query = new URLSearchParams()
    if (searchParams.get('page')) query.set('page', searchParams.get('page')!)
    if (searchParams.get('page_size')) query.set('page_size', searchParams.get('page_size')!)
    if (searchParams.get('as_of')) query.set('as_of', searchParams.get('as_of')!)

    const q = query.toString()
    const url = `${BACKEND}/news/symbol/${params.symbol}${q ? `?${q}` : ''}`
    const res = await fetch(url, { next: { revalidate: 60 } })

    if (!res.ok) {
      return NextResponse.json(getSeedItems(params.symbol, pageSize))
    }

    const data = await res.json()
    // Fall back to seed if backend returned empty
    if (!data.items?.length && SEED_NEWS[params.symbol]) {
      return NextResponse.json(getSeedItems(params.symbol, pageSize))
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json(getSeedItems(params.symbol, pageSize))
  }
}
