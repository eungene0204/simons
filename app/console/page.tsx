import { notFound } from 'next/navigation'
import { requireAdmin } from '@/lib/server/adminAuth'
import AdminConsole from '@/components/admin/AdminConsole'

export const dynamic = 'force-dynamic'

// 관리자 콘솔 — 비관리자에게는 404를 반환해 페이지 존재 자체를 숨긴다.
// 실제 보안은 이 게이트가 아니라 모든 /api/admin/* 라우트의 requireAdmin() 검사가 보장한다.
export default async function ConsolePage() {
  const admin = await requireAdmin()
  if (!admin) {
    notFound()
  }

  return <AdminConsole adminEmail={admin.email} />
}
