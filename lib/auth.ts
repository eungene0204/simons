import bcrypt from 'bcryptjs'
import jwt from 'jsonwebtoken'

// 세션 토큰 서명 키. 값이 없을 때 조용히 고정 문자열로 떨어지면 누구나 임의
// userId 토큰을 위조할 수 있으므로, 운영에서는 미설정을 실패로 드러낸다.
//
// 모듈 로드가 아니라 쓰는 시점에 확인한다 — Next 프로덕션 빌드는 라우트 모듈을 그냥
// import 해서 페이지 데이터를 수집하는데, 그 단계에는 런타임 환경변수가 없다.
// 로드 시점에 던지면 서명·검증을 한 번도 하지 않는 빌드가 통째로 깨진다.
function jwtSecret(): string {
  const secret = process.env.JWT_SECRET
  if (secret) return secret
  if (process.env.NODE_ENV === 'production') {
    throw new Error(
      'JWT_SECRET is not set. Refusing to sign or verify session tokens with a default key.'
    )
  }
  return 'dev-only-insecure-jwt-secret'
}

type SupabaseIdentity = {
  email: string
  emailVerified: boolean
  name: string | null
  avatarUrl: string | null
  uid: string
}

export type AuthTokenPayload = {
  userId: number
  avatarUrl?: string | null
}

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 10)
}

export async function verifyPassword(
  password: string,
  hashedPassword: string
): Promise<boolean> {
  return bcrypt.compare(password, hashedPassword)
}

export function generateToken(
  userId: number,
  profile?: { avatarUrl?: string | null }
): string {
  return jwt.sign({ userId, avatarUrl: profile?.avatarUrl ?? null }, jwtSecret(), { expiresIn: '7d' })
}

export function verifyToken(token: string): AuthTokenPayload | null {
  // 키 미설정은 설정 오류이므로 밖으로 던진다. 토큰이 틀린 것(만료·위조)만 null이다.
  const secret = jwtSecret()
  try {
    const decoded = jwt.verify(token, secret) as AuthTokenPayload
    return decoded
  } catch {
    return null
  }
}

export function isSupabaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  )
}

export async function verifySupabaseAccessToken(
  accessToken: string
): Promise<SupabaseIdentity> {
  if (!accessToken) {
    throw new Error('Supabase access token is required.')
  }

  if (!isSupabaseConfigured()) {
    throw new Error('Supabase environment variables are not configured.')
  }

  const { createClient } = await import('@supabase/supabase-js')

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL as string,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string,
    {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    }
  )

  const { data, error } = await supabase.auth.getUser(accessToken)

  if (error || !data.user) {
    throw new Error('Supabase access token verification failed.')
  }

  const email = data.user.email || ''
  const name =
    (typeof data.user.user_metadata?.full_name === 'string'
      ? data.user.user_metadata.full_name
      : null) ||
    (typeof data.user.user_metadata?.name === 'string'
      ? data.user.user_metadata.name
      : null)
  const avatarUrl =
    (typeof data.user.user_metadata?.avatar_url === 'string'
      ? data.user.user_metadata.avatar_url
      : null) ||
    (typeof data.user.user_metadata?.picture === 'string'
      ? data.user.user_metadata.picture
      : null)

  return {
    email,
    emailVerified: Boolean(
      data.user.email_confirmed_at || data.user.confirmed_at
    ),
    name,
    avatarUrl,
    uid: data.user.id,
  }
}
