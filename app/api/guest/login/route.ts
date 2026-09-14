import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import { prisma } from '@/lib/prisma'
import { generateToken, verifyPassword } from '@/lib/auth'
import { ensureUserBootstrap } from '@/lib/get-user'
import { consumeRateLimit } from '@/lib/server/rate-limit'
import { guestEmailFromId, normalizeGuestId } from '@/lib/server/guestAccounts'

// 게스트(테스터) 입장 — 운영자가 발급한 아이디·비밀번호로 로그인한다.
// 아이디는 합성 이메일(`<아이디>@guest.nullstock.im`)로 바꿔 User 행을 찾으므로
// 일반 회원 이메일로는 이 경로를 통과할 수 없다. 쿠키 계약은 /api/login과 같다.

export const dynamic = 'force-dynamic'

const INVALID_CREDENTIALS = '아이디 또는 비밀번호가 올바르지 않습니다.'
const RATE_WINDOW_MS = 15 * 60 * 1000

function clientIp(request: NextRequest): string {
  const forwarded = request.headers.get('x-forwarded-for')
  if (forwarded) return forwarded.split(',')[0].trim()
  return request.headers.get('x-real-ip') || 'unknown'
}

export async function POST(request: NextRequest) {
  try {
    // 비밀번호가 5자로 짧다 — 무차별 대입은 레이트리밋(IP 15분 30회·아이디 15분 10회)으로 막는다.
    if (!consumeRateLimit(`guest:login:ip:${clientIp(request)}`, 30, RATE_WINDOW_MS)) {
      return NextResponse.json(
        { error: '시도 횟수가 너무 많습니다. 잠시 후 다시 시도해주세요.' },
        { status: 429 }
      )
    }

    const body = await request.json()
    const rawId = typeof body?.guestId === 'string' ? body.guestId : ''
    const password = typeof body?.password === 'string' ? body.password : ''

    if (!rawId.trim() || !password) {
      return NextResponse.json(
        { error: '아이디와 비밀번호를 입력해주세요.' },
        { status: 400 }
      )
    }

    const guestId = normalizeGuestId(rawId)
    if (!guestId) {
      return NextResponse.json({ error: INVALID_CREDENTIALS }, { status: 401 })
    }

    if (!consumeRateLimit(`guest:login:id:${guestId}`, 10, RATE_WINDOW_MS)) {
      return NextResponse.json(
        { error: '시도 횟수가 너무 많습니다. 잠시 후 다시 시도해주세요.' },
        { status: 429 }
      )
    }

    const user = await prisma.user.findUnique({
      where: { email: guestEmailFromId(guestId) },
    })

    if (!user || !(await verifyPassword(password, user.password))) {
      return NextResponse.json({ error: INVALID_CREDENTIALS }, { status: 401 })
    }

    if (user.status !== 'ACTIVE') {
      return NextResponse.json(
        { error: '이용이 제한된 계정입니다.' },
        { status: 403 }
      )
    }

    await ensureUserBootstrap(user.id)

    await prisma.user.update({
      where: { id: user.id },
      data: { lastLoginAt: new Date() },
    })

    const token = generateToken(user.id)

    const cookieStore = await cookies()
    cookieStore.set('token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7, // 7 days
    })

    return NextResponse.json(
      {
        message: '로그인 성공',
        user: { id: user.id, email: user.email, name: user.name, avatarUrl: null },
      },
      { status: 200 }
    )
  } catch (error) {
    console.error('Guest login error:', error)
    return NextResponse.json(
      { error: '서버 오류가 발생했습니다.' },
      { status: 500 }
    )
  }
}
