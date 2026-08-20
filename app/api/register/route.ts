// 이메일 가입 2단계 — 인증번호 확인 + 계정 생성.
//
// 보안 설계
// - 인증번호를 통과해야만 계정이 생긴다(이메일 소유 증명). 코드 비교는 타이밍세이프.
// - 잘못된 코드는 시도 횟수를 누적하고, 상한(5회) 도달 시 재발송을 요구한다 — 6자리
//   코드 무차별 대입 차단. IP당 시간당 30회 레이트리밋을 추가로 둔다.
// - 비밀번호 정책: 8~72자 + 영문·숫자 포함. 저장은 bcrypt 해시.
// - 가입 성공 시 바로 로그인 쿠키를 발급한다(방금 이메일 소유를 증명했으므로 안전).

import { NextRequest, NextResponse } from 'next/server'
import { timingSafeEqual } from 'crypto'
import { cookies } from 'next/headers'
import { prisma } from '@/lib/prisma'
import { generateToken, hashPassword } from '@/lib/auth'
import { ensureUserBootstrap } from '@/lib/get-user'
import { consumeRateLimit } from '@/lib/server/rate-limit'
import {
  MAX_CODE_ATTEMPTS,
  hashVerificationCode,
  isAcceptablePassword,
  isEmailSignupEnabled,
  normalizeEmail,
} from '@/lib/server/email-verification'

function clientIp(request: NextRequest): string {
  const forwarded = request.headers.get('x-forwarded-for')
  if (forwarded) return forwarded.split(',')[0].trim()
  return 'unknown'
}

export async function POST(request: NextRequest) {
  // 테스트용 한시 기능 킬 스위치(EMAIL_SIGNUP_ENABLED=off) — 관리자 콘솔 선례대로 404 은닉
  if (!isEmailSignupEnabled()) {
    return NextResponse.json({ error: 'Not Found' }, { status: 404 })
  }
  try {
    const body = await request.json()
    const { name, password, code, termsAgreed } = body ?? {}
    const email = normalizeEmail(body?.email)

    const ip = clientIp(request)
    if (!consumeRateLimit(`register:submit:ip:${ip}`, 30, 60 * 60 * 1000)) {
      return NextResponse.json(
        { error: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.' },
        { status: 429 }
      )
    }

    if (!email) {
      return NextResponse.json(
        { error: '올바른 이메일 주소를 입력해주세요.' },
        { status: 400 }
      )
    }

    const trimmedName = typeof name === 'string' ? name.trim() : ''
    if (!trimmedName || trimmedName.length > 50) {
      return NextResponse.json(
        { error: '이름을 입력해주세요. (최대 50자)' },
        { status: 400 }
      )
    }

    if (!isAcceptablePassword(password)) {
      return NextResponse.json(
        { error: '비밀번호는 8자 이상이며 영문과 숫자를 모두 포함해야 합니다.' },
        { status: 400 }
      )
    }

    if (termsAgreed !== true) {
      return NextResponse.json(
        { error: '만 14세 이상 확인과 약관 동의가 필요합니다.' },
        { status: 400 }
      )
    }

    if (typeof code !== 'string' || !/^\d{6}$/.test(code)) {
      return NextResponse.json(
        { error: '인증번호 6자리를 입력해주세요.' },
        { status: 400 }
      )
    }

    const verification = await prisma.emailVerification.findUnique({
      where: { email },
    })

    if (!verification || verification.expiresAt.getTime() < Date.now()) {
      return NextResponse.json(
        { error: '인증번호가 만료되었거나 발송되지 않았습니다. 다시 요청해주세요.' },
        { status: 400 }
      )
    }

    if (verification.attempts >= MAX_CODE_ATTEMPTS) {
      return NextResponse.json(
        { error: '인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요.' },
        { status: 400 }
      )
    }

    const expected = Buffer.from(verification.codeHash, 'hex')
    const actual = Buffer.from(hashVerificationCode(code), 'hex')
    const codeMatches =
      expected.length === actual.length && timingSafeEqual(expected, actual)

    if (!codeMatches) {
      await prisma.emailVerification.update({
        where: { email },
        data: { attempts: { increment: 1 } },
      })
      return NextResponse.json(
        { error: '인증번호가 올바르지 않습니다.' },
        { status: 400 }
      )
    }

    // 이메일 소유는 방금 증명됐으므로, 여기서의 중복 안내는 열거 누설이 아니다.
    const existingUser = await prisma.user.findUnique({ where: { email } })
    if (existingUser) {
      return NextResponse.json(
        { error: '이미 가입된 이메일입니다.' },
        { status: 400 }
      )
    }

    const hashedPassword = await hashPassword(password)
    let user
    try {
      user = await prisma.user.create({
        data: {
          email,
          name: trimmedName,
          password: hashedPassword,
          updatedAt: new Date(),
        },
      })
    } catch (createError) {
      // 동시 가입 레이스 — unique(email) 위반은 중복 안내로 수렴시킨다.
      if (
        createError instanceof Error &&
        'code' in createError &&
        (createError as { code?: string }).code === 'P2002'
      ) {
        return NextResponse.json(
          { error: '이미 가입된 이메일입니다.' },
          { status: 400 }
        )
      }
      throw createError
    }

    await prisma.emailVerification.deleteMany({ where: { email } })

    // 가입 직후 자동 로그인 — /api/login과 동일한 쿠키 계약.
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
      maxAge: 60 * 60 * 24 * 7,
    })

    return NextResponse.json(
      {
        message: '회원가입이 완료되었습니다.',
        user: { id: user.id, email: user.email, name: user.name },
      },
      { status: 201 }
    )
  } catch (error) {
    console.error('Registration error:', error)
    return NextResponse.json(
      { error: '서버 오류가 발생했습니다.' },
      { status: 500 }
    )
  }
}
