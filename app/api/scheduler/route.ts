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
 *   market-open    — 09:00 KST: auto 모드 계좌 전체 시작
 *   market-refresh — 09:05~15:25 KST: 실행 중인 계좌 전체 새로고침
 *   market-close   — 15:30 KST: 실행 중인 계좌 전체 일시정지
 *
 * 보안: SCHEDULER_SECRET 환경변수가 설정된 경우 Authorization 헤더 검증
 */

import { NextResponse } from "next/server";
import { runSchedulerAction } from "@/lib/server/scheduler-actions";

const SCHEDULER_SECRET = process.env.SCHEDULER_SECRET;

function isAuthorized(request: Request): boolean {
  if (!SCHEDULER_SECRET) return true; // 미설정 시 개발 편의상 허용
  const auth = request.headers.get("Authorization");
  return auth === `Bearer ${SCHEDULER_SECRET}`;
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
