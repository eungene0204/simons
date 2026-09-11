import { prisma } from '@/lib/prisma'
import { getOwnershipContext, withOwnership } from '@/lib/get-user'

/**
 * 세션 사용자가 소유한 가상 계좌인지 확인하고 계좌 ID를 돌려준다.
 *
 * 비로그인이면 getOwnershipContext가 UnauthorizedAccessError를 던지므로,
 * 호출부는 isUnauthorizedAccessError로 401을 낸다. 로그인했지만 남의 계좌면
 * null을 돌려준다 — 호출부는 계좌 존재 여부를 알리지 않도록 404로 응답한다.
 */
export async function findOwnedAccountId(accountId: string): Promise<string | null> {
  const { userId } = await getOwnershipContext()
  const account = await prisma.virtualAccount.findFirst({
    where: withOwnership({ id: accountId }, userId),
    select: { id: true },
  })
  return account?.id ?? null
}
