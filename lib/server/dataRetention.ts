import type { PrismaClient } from "@prisma/client";

/**
 * 보존기간 정책 — 목적을 다한 개인정보·운영 로그를 기한이 지나면 지운다.
 *
 * 개인정보보호법 제21조는 보유 목적을 달성하면 지체 없이 파기하도록 한다. 반대로
 * 법이 보존을 요구하는 기록(결제)은 기한 전에 지우면 안 된다. 아래 표는 그 두 요구를
 * 데이터별로 갈라 놓은 것이며, 기간은 전부 여기서만 정한다.
 *
 * | 대상                | 기간        | 근거                                                      |
 * |---------------------|-------------|-----------------------------------------------------------|
 * | ChatQaLog           | 90일        | 사용자 발화 원문. 답변 품질 점검이 목적이고 그 목적은 분기면 끝난다 |
 * | EmailVerification   | 만료 후 1일 | 인증번호 해시. 만료된 순간 목적이 끝난다                    |
 * | PaymentWebhookEvent | 180일       | 재전송 멱등 키. PSP 재전송 창(수일)보다 넉넉히 잡는다        |
 * | AdminAuditLog       | 3년         | 개인정보 접속기록 최소 1년(안전성 확보조치 기준 제8조) +
 * |                     |             | 소비자 불만·분쟁 처리 기록 3년(전자상거래법 제6조)          |
 *
 * 지우지 않는 것:
 * - `PaymentOrder` — 대금결제·재화공급 기록으로 전자상거래법상 5년 보존 의무가 있다.
 *   계정 삭제 시에도 남긴다.
 * - `VirtualMarketLog`·`VirtualOrder`·`VirtualPosition` 등 모의투자 기록 — 개인정보처리방침
 *   제4조가 "이용자가 삭제하거나 계정이 종료될 때까지 보유"라고 약속한 이용자 데이터다.
 *   기간을 걸어 지우면 그 약속과 어긋나므로 이 잡의 대상이 아니다.
 */
export const RETENTION_DAYS = {
  chatQaLog: 90,
  emailVerification: 1, // 만료 시각 기준
  paymentWebhookEvent: 180,
  adminAuditLog: 365 * 3,
} as const;

export type RetentionTarget = keyof typeof RETENTION_DAYS;

export type RetentionSummary = Record<RetentionTarget, number>;

function cutoff(now: Date, days: number): Date {
  return new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
}

/**
 * 기한이 지난 행을 지우고 대상별 삭제 건수를 돌려준다.
 *
 * 한 대상이 실패해도 나머지는 계속 지운다 — 보존기간 초과 상태를 남겨 두는 쪽이
 * 더 나쁘다. 실패는 로그로 드러낸다.
 */
export async function purgeExpiredRecords(
  prisma: PrismaClient,
  now: Date = new Date()
): Promise<RetentionSummary> {
  const summary: RetentionSummary = {
    chatQaLog: 0,
    emailVerification: 0,
    paymentWebhookEvent: 0,
    adminAuditLog: 0,
  };

  const jobs: Array<[RetentionTarget, () => Promise<{ count: number }>]> = [
    [
      "chatQaLog",
      () =>
        prisma.chatQaLog.deleteMany({
          where: { createdAt: { lt: cutoff(now, RETENTION_DAYS.chatQaLog) } },
        }),
    ],
    [
      // 인증번호는 발송 시각이 아니라 만료 시각을 기준으로 센다(재발송으로 만료가 밀린다).
      "emailVerification",
      () =>
        prisma.emailVerification.deleteMany({
          where: { expiresAt: { lt: cutoff(now, RETENTION_DAYS.emailVerification) } },
        }),
    ],
    [
      "paymentWebhookEvent",
      () =>
        prisma.paymentWebhookEvent.deleteMany({
          where: { receivedAt: { lt: cutoff(now, RETENTION_DAYS.paymentWebhookEvent) } },
        }),
    ],
    [
      "adminAuditLog",
      () =>
        prisma.adminAuditLog.deleteMany({
          where: { createdAt: { lt: cutoff(now, RETENTION_DAYS.adminAuditLog) } },
        }),
    ],
  ];

  for (const [target, run] of jobs) {
    try {
      summary[target] = (await run()).count;
    } catch (error) {
      console.error(`[Retention] ${target} 파기 실패:`, error);
    }
  }

  return summary;
}
