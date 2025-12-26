import { NextResponse } from 'next/server'
import { getCurrentUser } from '@/lib/get-user'

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


