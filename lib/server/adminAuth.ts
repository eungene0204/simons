// 관리자 인증/감사 로그 헬퍼
//
// 보안 원칙: UI 숨김은 보안이 아니다. 모든 관리자 API·페이지는 서버에서
// requireAdmin()으로 권한을 검사한다. 권한이 없으면 404로 응답해
// 관리자 콘솔의 존재 자체를 숨긴다.
//
// ADMIN 권한 부여는 DB에서만 한다 (관리자 화면/API로 role 변경 불가).

import { cookies, headers } from 'next/headers'
import { verifyToken } from '@/lib/auth'
import { prisma } from '@/lib/prisma'

export interface AdminUser {
  id: number
  email: string
  name: string
}

/**
 * 현재 요청이 활성(ACTIVE) 상태의 ADMIN 사용자인지 서버에서 검증한다.
 * 미로그인 / 비관리자 / 정지·삭제 계정이면 null을 반환한다.
 */
export async function requireAdmin(): Promise<AdminUser | null> {
  try {
    const cookieStore = await cookies()
    const token = cookieStore.get('token')?.value
    if (!token) return null

    const decoded = verifyToken(token)
    if (!decoded) return null

    const user = await prisma.user.findUnique({
      where: { id: decoded.userId },
      select: { id: true, email: true, name: true, role: true, status: true },
    })

    if (!user || user.role !== 'ADMIN' || user.status !== 'ACTIVE') return null

    return { id: user.id, email: user.email, name: user.name }
  } catch {
    return null
  }
}

/** 요청 IP (프록시 뒤에서는 x-forwarded-for 첫 항목) */
export async function getRequestIp(): Promise<string | null> {
  try {
    const headerStore = await headers()
    const forwarded = headerStore.get('x-forwarded-for')
    if (forwarded) return forwarded.split(',')[0].trim()
    return headerStore.get('x-real-ip')
  } catch {
    return null
  }
}

export interface AuditLogEntry {
  action: string
  targetType?: string
  targetId?: string
  targetUserId?: number
  before?: unknown
  after?: unknown
}

/** 관리자 작업 감사 로그 기록 — 모든 변경 작업 후 반드시 호출한다. */
export async function writeAuditLog(
  admin: AdminUser,
  entry: AuditLogEntry
): Promise<void> {
  await prisma.adminAuditLog.create({
    data: {
      adminId: admin.id,
      adminEmail: admin.email,
      action: entry.action,
      targetType: entry.targetType ?? null,
      targetId: entry.targetId ?? null,
      targetUserId: entry.targetUserId ?? null,
      beforeJson: entry.before === undefined ? null : JSON.stringify(entry.before),
      afterJson: entry.after === undefined ? null : JSON.stringify(entry.after),
      ip: await getRequestIp(),
    },
  })
}
