import { NextResponse } from 'next/server'
import { getCurrentUser } from '@/lib/get-user'

// This route returns {user:null} (200) when unauthenticated instead of throwing,
// so Next prerenders it as static and serves a baked-in {user:null} from the
// Full Route Cache — ignoring the real session cookie. The client AuthSessionGuard
// then bounces logged-in users off every protected page. Force dynamic so it
// always reads the request cookie.
export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const user = await getCurrentUser()

    if (!user) {
      return NextResponse.json({ user: null }, { status: 200 })
    }

    return NextResponse.json({ user }, { status: 200 })
  } catch (error) {
    console.error('Get user error:', error)
    return NextResponse.json({ user: null }, { status: 200 })
  }
}


