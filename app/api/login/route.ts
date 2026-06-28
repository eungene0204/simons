import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import {
  generateToken,
  hashPassword,
  verifySupabaseAccessToken,
  verifyPassword,
} from '@/lib/auth'
import { ensureUserBootstrap } from '@/lib/get-user'
import { cookies } from 'next/headers'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { email, password, supabaseAccessToken } = body

    if (supabaseAccessToken) {
      // 토큰 검증만 별도 try로 격리한다. 검증 이후의 DB 작업(유저 조회/생성,
      // 부트스트랩) 오류가 "토큰 검증 실패(401)"로 둔갑하면 안 되므로, DB 오류는
      // 바깥 catch로 흘려보내 500 서버 오류로 드러나게 한다.
      let identity
      try {
        identity = await verifySupabaseAccessToken(supabaseAccessToken)
      } catch (supabaseError) {
        const message =
          supabaseError instanceof Error
            ? supabaseError.message
            : 'Google 로그인 검증에 실패했습니다.'
        const status = message.includes('not configured') ? 500 : 401

        return NextResponse.json(
          {
            error:
              status === 500
                ? 'Supabase 서버 설정이 완료되지 않았습니다.'
                : 'Google 로그인 검증에 실패했습니다.',
          },
          { status }
        )
      }

      if (!identity.email || !identity.emailVerified) {
        return NextResponse.json(
          { error: 'Google 계정 이메일을 확인할 수 없습니다.' },
          { status: 401 }
        )
      }

      let user = await prisma.user.findUnique({
        where: { email: identity.email },
      })

      if (!user) {
        user = await prisma.user.create({
          data: {
            email: identity.email,
            name: identity.name || identity.email.split('@')[0],
            password: await hashPassword(
              `google-oauth:${identity.uid}:${crypto.randomUUID()}`
            ),
            updatedAt: new Date(),
          },
        })
      }

      await ensureUserBootstrap(user.id)

      const token = generateToken(user.id, { avatarUrl: identity.avatarUrl })

      const cookieStore = await cookies()
      cookieStore.set('token', token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 7,
      })

      return NextResponse.json(
        {
          message: '로그인 성공',
          user: { id: user.id, email: user.email, name: user.name, avatarUrl: identity.avatarUrl },
        },
        { status: 200 }
      )
    }

    // Validation
    if (!email || !password) {
      return NextResponse.json(
        { error: '이메일과 비밀번호를 입력해주세요.' },
        { status: 400 }
      )
    }

    // Find user
    const user = await prisma.user.findUnique({
      where: { email },
    })

    if (!user) {
      return NextResponse.json(
        { error: '이메일 또는 비밀번호가 올바르지 않습니다.' },
        { status: 401 }
      )
    }

    // Verify password
    const isValid = await verifyPassword(password, user.password)

    if (!isValid) {
      return NextResponse.json(
        { error: '이메일 또는 비밀번호가 올바르지 않습니다.' },
        { status: 401 }
      )
    }

    await ensureUserBootstrap(user.id)

    // Generate token
    const token = generateToken(user.id)

    // Set cookie
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
    console.error('Login error:', error)
    return NextResponse.json(
      { error: '서버 오류가 발생했습니다.' },
      { status: 500 }
    )
  }
}
