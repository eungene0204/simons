import { cookies } from 'next/headers'
import { verifyToken } from './auth'
import { prisma } from './prisma'

export class UnauthorizedAccessError extends Error {
  constructor(message = 'Unauthorized') {
    super(message)
    this.name = 'UnauthorizedAccessError'
  }
}

export async function getCurrentUser() {
  try {
    const cookieStore = await cookies()
    const token = cookieStore.get('token')?.value

    if (!token) {
      return null
    }

    const decoded = verifyToken(token)
    if (!decoded) {
      return null
    }

    const user = await prisma.user.findUnique({
      where: { id: decoded.userId },
      select: { id: true, email: true, name: true },
    })

    return user ? { ...user, avatarUrl: decoded.avatarUrl ?? null } : null
  } catch {
    return null
  }
}

export async function getOwnershipContext() {
  const user = await getCurrentUser()

  if (user) {
    return { userId: user.id }
  }

  if (process.env.NODE_ENV === 'test') {
    return { userId: null }
  }

  throw new UnauthorizedAccessError()
}

export function withOwnership<T extends Record<string, unknown>>(
  where: T,
  userId: number | null
): T & Record<string, unknown> {
  if (userId == null) {
    return where
  }

  return {
    ...where,
    userId,
  }
}

export function isUnauthorizedAccessError(error: unknown): boolean {
  return error instanceof UnauthorizedAccessError
}

export async function ensureUserBootstrap(userId: number) {
  const existingGroup = await prisma.watchlistGroup.findFirst({
    where: { userId },
    select: { id: true },
  })

  if (!existingGroup) {
    await prisma.watchlistGroup.create({
      data: {
        id: crypto.randomUUID(),
        userId,
        name: '기본 관심종목',
        color: '#3B82F6',
      },
    })
  }
}
