import bcrypt from 'bcryptjs'
import jwt from 'jsonwebtoken'

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production'

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
  return jwt.sign({ userId, avatarUrl: profile?.avatarUrl ?? null }, JWT_SECRET, { expiresIn: '7d' })
}

export function verifyToken(token: string): AuthTokenPayload | null {
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as AuthTokenPayload
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
