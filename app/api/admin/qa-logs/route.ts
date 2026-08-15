import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin } from '@/lib/server/adminAuth'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 30

// GET: 전략연구소 대화 기록 조회 (기록은 감사 로그와 같이 삭제 API를 제공하지 않는다)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const page = Math.max(1, Number(params.get('page')) || 1)
    const email = params.get('email')?.trim() || ''
    const keyword = params.get('keyword')?.trim() || ''
    const answerKind = params.get('answerKind')?.trim() || ''
    const sessionId = params.get('sessionId')?.trim() || ''

    const where: Record<string, unknown> = {}
    if (email) where.userEmail = { contains: email, mode: 'insensitive' }
    if (answerKind) where.answerKind = answerKind
    if (sessionId) where.sessionId = sessionId
    // 질문과 답변 어느 쪽에 있어도 찾는다.
    if (keyword) {
      where.OR = [
        { question: { contains: keyword, mode: 'insensitive' } },
        { answer: { contains: keyword, mode: 'insensitive' } },
      ]
    }

    const [total, logs] = await Promise.all([
      prisma.chatQaLog.count({ where }),
      prisma.chatQaLog.findMany({
        where,
        // 한 대화를 지정해 볼 때는 주고받은 순서대로 읽히도록 오름차순으로 둔다.
        orderBy: sessionId ? { turnIndex: 'asc' } : { createdAt: 'desc' },
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
      }),
    ])

    return NextResponse.json({ total, page, pageSize: PAGE_SIZE, logs })
  } catch (error) {
    console.error('Admin QA log list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
