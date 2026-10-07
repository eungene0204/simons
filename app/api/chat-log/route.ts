import { createHash } from 'crypto'
import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/get-user'
import { strategySnapshotJson } from '@/lib/server/qaLogStrategy'

export const dynamic = 'force-dynamic'

// 전략연구소 대화 한 턴(질문 + 그 턴의 답변)을 기록한다.
// Delivery IDs make acknowledged retries idempotent without blocking the conversation.
// 비로그인 대화도 기록한다(userId=null). 답변 품질 점검용이며 사용자에게 노출하지 않는다.

// 저장 상한 — 넘치는 입력으로 로그 테이블이 부풀지 않게 자른다.
const MAX_QUESTION = 4_000
const MAX_ANSWER = 20_000
const MAX_SESSION_ID = 100

const ANSWER_KINDS = new Set([
  'error',
  'clarification',
  'strategy',
  'coach',
  'info',
  'text',
])

function text(value: unknown, limit: number): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  return trimmed.slice(0, limit)
}

export async function POST(request: NextRequest) {
  let body: Record<string, unknown>
  try {
    body = (await request.json()) as Record<string, unknown>
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return NextResponse.json({ detail: 'Invalid payload' }, { status: 400 })
  }

  const sessionId = text(body.sessionId, MAX_SESSION_ID)
  const question = text(body.question, MAX_QUESTION)
  const answer = text(body.answer, MAX_ANSWER)
  const turnIndex = Number(body.turnIndex)
  const answerKind = typeof body.answerKind === 'string' ? body.answerKind : ''

  if (!sessionId || !question || !answer || !Number.isInteger(turnIndex) || turnIndex < 0) {
    return NextResponse.json({ detail: 'Invalid payload' }, { status: 400 })
  }
  if (!ANSWER_KINDS.has(answerKind)) {
    return NextResponse.json({ detail: 'Unknown answerKind' }, { status: 400 })
  }

  const deliveryId = body.deliveryId
  if (deliveryId !== undefined && (
    typeof deliveryId !== 'string' || !deliveryId || deliveryId.length > 100 ||
    !(body.ownerId === null || (Number.isSafeInteger(body.ownerId) && Number(body.ownerId) > 0))
  )) {
    return NextResponse.json({ detail: 'Invalid delivery identity' }, { status: 400 })
  }

  const latency = body.latencyMs == null ? NaN : Number(body.latencyMs)
  const latencyMs = Number.isFinite(latency) && latency >= 0 ? Math.round(latency) : null

  try {
    const user = await getCurrentUser()
    if (deliveryId !== undefined && body.ownerId !== (user?.id ?? null)) {
      return NextResponse.json({ detail: 'Log owner changed' }, { status: 409 })
    }
    const id = deliveryId === undefined ? undefined : createHash('sha256')
      .update(JSON.stringify([user?.id ?? null, deliveryId])).digest('hex')
    await prisma.chatQaLog.create({
      data: {
        ...(id ? { id } : {}),
        userId: user?.id ?? null,
        userEmail: user?.email ?? null,
        sessionId,
        turnIndex,
        question,
        answer,
        answerKind,
        chipAnswer: body.chipAnswer === true,
        latencyMs,
        strategySnapshot: strategySnapshotJson(body.strategy),
      },
    })
    return new NextResponse(null, { status: 204 })
  } catch (error) {
    if (deliveryId !== undefined && (error as { code?: string })?.code === 'P2002') {
      return new NextResponse(null, { status: 204 })
    }
    console.error('Chat QA log write error:', error)
    return NextResponse.json({ detail: 'Internal error' }, { status: 500 })
  }
}
