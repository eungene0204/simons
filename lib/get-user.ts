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
      select: { id: true, email: true, name: true, status: true },
    })

    // 정지(SUSPENDED)·삭제(DELETED) 계정은 유효한 토큰이 있어도 세션을 인정하지 않는다
    if (!user || user.status !== 'ACTIVE') {
      return null
    }

    return {
      id: user.id,
      email: user.email,
      name: user.name,
      avatarUrl: decoded.avatarUrl ?? null,
    }
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
  await prisma.$transaction(async (tx) => {
    const existingGroup = await tx.watchlistGroup.findFirst({
      where: { userId },
      select: { id: true },
    })

    if (!existingGroup) {
      await tx.watchlistGroup.create({
        data: {
          id: crypto.randomUUID(),
          userId,
          name: '기본 관심종목',
          color: '#3B82F6',
        },
      })
    }
  })
}
