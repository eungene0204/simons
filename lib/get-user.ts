import { cookies } from 'next/headers'
import { verifyToken } from './auth'
import { prisma } from './prisma'

export class UnauthorizedAccessError extends Error {
  constructor(message = 'Unauthorized') {
    super(message)
    this.name = 'UnauthorizedAccessError'
  }
}

/** 세션 쿠키의 토큰을 해석한다 (DB 조회 없음) */
async function getDecodedToken() {
  try {
    const cookieStore = await cookies()
    const token = cookieStore.get('token')?.value
    if (!token) {
      return null
    }
    return verifyToken(token) ?? null
  } catch {
    return null
  }
}

/**
 * DB 조회 없이 토큰에서 userId만 해석한다.
 * 계정 상태(ACTIVE) 검증은 하지 않으므로, 호출부는 반드시 assertActiveUser를
 * (다른 DB 조회와 병렬로) 함께 실행해야 한다 — 원격 DB 왕복을 줄이기 위한 분리.
 */
export async function getSessionUserId(): Promise<number | null> {
  const decoded = await getDecodedToken()
  return decoded?.userId ?? null
}

/** 계정이 존재하고 ACTIVE인지 검증 — 아니면 UnauthorizedAccessError throw */
export async function assertActiveUser(userId: number): Promise<void> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { status: true },
  })
  if (!user || user.status !== 'ACTIVE') {
    throw new UnauthorizedAccessError()
  }
}

export async function getCurrentUser() {
  try {
    const decoded = await getDecodedToken()
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
