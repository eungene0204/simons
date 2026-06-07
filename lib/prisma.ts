import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

function createPrismaClient(): PrismaClient {
  // SQLite는 동시 writer가 하나뿐이라, 단일 연결로 쿼리를 직렬화해
  // 프로세스 내부 쓰기 락 경합(SQLITE_BUSY)을 막는다.
  const baseUrl = process.env.DATABASE_URL ?? ''
  const url = baseUrl
    ? `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}connection_limit=1`
    : baseUrl

  const client = url
    ? new PrismaClient({ datasources: { db: { url } } })
    : new PrismaClient()

  // WAL: 읽기/쓰기 동시성 향상(영구 설정), busy_timeout: 락 만나면 즉시 실패 대신 대기
  client.$queryRawUnsafe('PRAGMA journal_mode=WAL').catch(() => {})
  client.$queryRawUnsafe('PRAGMA busy_timeout=10000').catch(() => {})

  return client
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma


