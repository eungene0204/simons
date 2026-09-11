/**
 * POST /api/scheduler
 *
 * 스케줄러 전용 배치 엔드포인트 (외부 호출용 얇은 HTTP 래퍼).
 * 핵심 로직은 lib/server/scheduler-actions(runSchedulerAction)에 있으며,
 * 인-프로세스 스케줄러(lib/scheduler)는 이 라우트를 HTTP 로 호출하지 않고
 * runSchedulerAction 을 직접 호출한다.
 *
 * action:
 *   pre-market     — 08:50 KST: 추적 종목 시세 캐시 사전 로드
 *   market-open    — 09:00 KST: auto 모드 계좌 전체 시작 (running 전환)
 *   market-refresh — (비활성) 자동매매 체결은 VirtualTrader 로 일원화됨 → no-op
 *   market-close   — 15:30 KST: 실행 중인 계좌 전체 일시정지 (paused 전환)
 *
 * 보안: Authorization 헤더의 SCHEDULER_SECRET을 검증한다. 운영(NODE_ENV=production)에서
 *       시크릿이 없으면 아무도 부를 수 없다(fail closed).
 */

import { NextResponse } from "next/server";
import { runSchedulerAction } from "@/lib/server/scheduler-actions";

const SCHEDULER_SECRET = process.env.SCHEDULER_SECRET;

function isAuthorized(request: Request): boolean {
  if (SCHEDULER_SECRET) {
    return request.headers.get("Authorization") === `Bearer ${SCHEDULER_SECRET}`;
  }
  // 시크릿 미설정은 개발 편의일 뿐이다. 운영에서 열어 두면 외부에서 전 사용자의
  // 자동매매 계좌를 일괄 시작·정지할 수 있으므로 닫는 쪽으로 실패한다.
  return process.env.NODE_ENV !== "production";
}

export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { action } = await request.json();
  const result = await runSchedulerAction(action);

  if ("error" in result) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
