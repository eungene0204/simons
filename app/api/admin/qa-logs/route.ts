import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin } from '@/lib/server/adminAuth'
import { parseStrategySnapshot, type StoredStrategySnapshot } from '@/lib/server/qaLogStrategy'
import { collectQaTurns, type QaChatMessage } from '@/app/analytics/new/qaLog'
import { RECOVERED_QA_PREFIX } from '@/lib/server/consoleHistoryRecovery'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 30

// 답변 텍스트에서 전략 카드가 있던 턴의 표지 — 우리가 쓴 자리표시자(app/analytics/new/qaLog.ts)
const STRATEGY_CARD_MARKER = '[전략 요약 카드]'

type StrategySource = 'log' | 'chat_snapshot'

/**
 * 전략 카드 칸(strategySnapshot)이 생기기 전(2026-09-30 이전)의 턴은 카드 내용이 없다.
 * 사용자의 대화 기록(StrategyChatLog — 세션 id가 같다)이 아직 남아 있으면 그 스냅샷에서 같은
 * 번호의 턴 카드를 찾아 보여 준다(읽기만 한다). 대화 기록은 계정당 최근 30개라 오래된 턴은 없다.
 */
async function recoverFromChatSnapshots(
  logs: { userId: number | null; sessionId: string; turnIndex: number }[]
): Promise<Map<string, StoredStrategySnapshot>> {
  const recovered = new Map<string, StoredStrategySnapshot>()
  const keys = logs.filter((l) => l.userId != null)
  if (keys.length === 0) return recovered
  const chats = await prisma.strategyChatLog.findMany({
    where: { OR: keys.map((l) => ({ userId: l.userId!, sessionId: l.sessionId })) },
    select: { userId: true, sessionId: true, snapshot: true },
  })
  for (const chat of chats) {
    let messages: QaChatMessage[] = []
    try {
      const snapshot = JSON.parse(chat.snapshot)
      messages = Array.isArray(snapshot?.messages) ? snapshot.messages : []
    } catch {
      continue
    }
    for (const turn of collectQaTurns(messages)) {
      if (turn.strategy) {
        recovered.set(`${chat.userId}:${chat.sessionId}:${turn.turnIndex}`, turn.strategy)
      }
    }
  }
  return recovered
}

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
    const userId = Number(params.get('userId')) || null
    // 전략 카드가 뜬 턴만 — 사용자가 입력한 전략과 우리의 해석을 모아 볼 때
    const strategyOnly = params.get('strategyOnly') === '1'

    const where: Record<string, unknown> = {}
    if (email) where.userEmail = { contains: email, mode: 'insensitive' }
    if (answerKind) where.answerKind = answerKind
    if (sessionId) where.sessionId = sessionId
    if (userId) where.userId = userId
    if (strategyOnly) where.answer = { contains: STRATEGY_CARD_MARKER }
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

    const missing = logs.filter((l) => !l.strategySnapshot && l.answer.includes(STRATEGY_CARD_MARKER))
    const recovered = missing.length > 0 ? await recoverFromChatSnapshots(missing) : new Map()

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      logs: logs.map(({ strategySnapshot, ...log }) => {
        const stored = parseStrategySnapshot(strategySnapshot)
        const fallback = stored ? null : recovered.get(`${log.userId}:${log.sessionId}:${log.turnIndex}`)
        const strategy = stored ?? fallback ?? null
        const strategySource: StrategySource | null = stored
          ? stored.recovery?.source === 'StrategyChatLog' ? 'chat_snapshot' : 'log'
          : fallback ? 'chat_snapshot' : null
        return { ...log, strategy, strategySource, recoveredFromSnapshot: log.id.startsWith(RECOVERED_QA_PREFIX) }
      }),
    })
  } catch (error) {
    console.error('Admin QA log list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
