// 이메일 가입 1단계 — 인증번호 발송.
//
// 보안 설계
// - 가입 여부 비노출(계정 열거 방지): 이미 가입된 이메일이어도 응답은 동일하다.
//   가입된 주소에는 인증번호 대신 "이미 가입됨" 안내 메일이 간다.
// - 코드 원문은 저장하지 않는다 — SHA-256 해시만 저장, 10분 만료.
// - 레이트리밋: IP당 시간당 20회, 이메일당 시간당 5회, 재발송 60초 쿨다운.
//   쿨다운·이메일 한도는 가입 여부 분기 전에 소비해 응답 차이가 생기지 않게 한다.

import { NextRequest, NextResponse } from 'next/server'
import { randomInt } from 'crypto'
import { prisma } from '@/lib/prisma'
import { consumeRateLimit } from '@/lib/server/rate-limit'
import {
  CODE_TTL_MS,
  hashVerificationCode,
  normalizeEmail,
} from '@/lib/server/email-verification'
import {
  sendAlreadyRegisteredEmail,
  sendVerificationEmail,
} from '@/lib/server/mailer'

function clientIp(request: NextRequest): string {
  const forwarded = request.headers.get('x-forwarded-for')
  if (forwarded) return forwarded.split(',')[0].trim()
  return 'unknown'
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const email = normalizeEmail(body?.email)

    if (!email) {
      return NextResponse.json(
        { error: '올바른 이메일 주소를 입력해주세요.' },
        { status: 400 }
      )
    }

    const ip = clientIp(request)
    if (!consumeRateLimit(`register:request-code:ip:${ip}`, 20, 60 * 60 * 1000)) {
      return NextResponse.json(
        { error: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.' },
        { status: 429 }
      )
    }
    // 쿨다운·이메일별 한도는 가입 여부와 무관하게 먼저 소비한다(응답 차이 = 열거 단서).
    if (!consumeRateLimit(`register:request-code:cooldown:${email}`, 1, 60 * 1000)) {
      return NextResponse.json(
        { error: '잠시 후 다시 요청할 수 있습니다.' },
        { status: 429 }
      )
    }
    if (!consumeRateLimit(`register:request-code:email:${email}`, 5, 60 * 60 * 1000)) {
      return NextResponse.json(
        { error: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.' },
        { status: 429 }
      )
    }

    const existingUser = await prisma.user.findUnique({ where: { email } })

    if (existingUser) {
      // 응답은 미가입 케이스와 동일하게 유지한다.
      await sendAlreadyRegisteredEmail(email)
      return NextResponse.json(
        { message: '인증번호를 발송했습니다. 메일함을 확인해주세요.' },
        { status: 200 }
      )
    }

    const code = randomInt(0, 1_000_000).toString().padStart(6, '0')
    const now = new Date()
    const codeHash = hashVerificationCode(code)
    const expiresAt = new Date(now.getTime() + CODE_TTL_MS)

    await prisma.emailVerification.upsert({
      where: { email },
      create: { email, codeHash, expiresAt, attempts: 0, lastSentAt: now },
      update: { codeHash, expiresAt, attempts: 0, lastSentAt: now },
    })

    await sendVerificationEmail(email, code)

    return NextResponse.json(
      { message: '인증번호를 발송했습니다. 메일함을 확인해주세요.' },
      { status: 200 }
    )
  } catch (error) {
    console.error('Verification code request error:', error)
    return NextResponse.json(
      { error: '인증 메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.' },
      { status: 500 }
    )
  }
}
