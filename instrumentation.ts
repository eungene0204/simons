/**
 * Next.js Instrumentation Hook
 *
 * 서버 시작 시 한 번 실행되며, 내장 스케줄러를 자동으로 시작한다.
 * https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
  // 서버 사이드에서만 실행 (Edge 런타임 제외)
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { startScheduler } = await import("./lib/scheduler");
    startScheduler();
  }
}
