// GA4 이벤트 전송 서비스 레이어 — 컴포넌트는 window.gtag를 직접 만지지 않고
// 이 모듈(trackEvent)만 호출한다. GA 초기화는 app/layout.tsx의
// <GoogleAnalytics>(@next/third-parties)가 담당하며, 여기서는 재초기화하지 않는다.

import type {
  AnalyticsEventMap,
  AnalyticsEventName,
  BacktestRunParams,
} from "./types";

type GtagFn = (...args: unknown[]) => void;

/** SSR·GA 미설정(NEXT_PUBLIC_GA_ID 없음)·스크립트 차단 환경에서는 null */
function getGtag(): GtagFn | null {
  if (typeof window === "undefined") return null;
  const gtag = (window as { gtag?: unknown }).gtag;
  return typeof gtag === "function" ? (gtag as GtagFn) : null;
}

/**
 * GA4 이벤트 전송. GA가 없거나 오류가 나도 서비스 동작에는 영향을 주지 않는다
 * (조용히 no-op). 파라미터 타입은 AnalyticsEventMap이 이벤트별로 강제한다.
 */
export function trackEvent<E extends AnalyticsEventName>(
  event: E,
  params: AnalyticsEventMap[E]
): void {
  try {
    const gtag = getGtag();
    if (!gtag) return;
    gtag("event", event, params);
  } catch {
    // GA 실패는 삼킨다 — 분석은 서비스의 부가 기능이다.
  }
}

/**
 * 백테스트 엔진 요청(BacktestRequest 형태의 구조화 객체)에서 backtest_run
 * 파라미터를 뽑는다. 입력은 이미 파싱·컴파일된 요청이므로 표기 정규화만 한다.
 */
export function backtestRunParamsFromRequest(req: unknown): BacktestRunParams {
  const r = (req ?? {}) as Record<string, unknown>;

  const universeId = String(r.universe_id ?? r.universeId ?? "").toLowerCase();
  let market = "UNKNOWN";
  if (universeId.startsWith("kospi")) market = "KOSPI";
  else if (universeId.startsWith("kosdaq")) market = "KOSDAQ";
  else if (universeId.startsWith("nasdaq")) market = "NASDAQ";
  else if (universeId.startsWith("nyse")) market = "NYSE";
  else if (universeId) market = universeId.toUpperCase(); // SP500·DOW30·ETF 등 거래소로 접히지 않는 유니버스

  const startDate = r.startDate ?? r.start_date;
  const endDate = r.endDate ?? r.end_date;
  const backtest_period =
    typeof startDate === "string" && typeof endDate === "string"
      ? `${startDate}~${endDate}`
      : String(r.period ?? "unknown");

  const symbols = r.symbols;

  return {
    strategy_name: String(r.strategy_name ?? r.name ?? "unnamed"),
    market,
    rebalance_period: String(r.rebalancing_period ?? "none"),
    backtest_period,
    ...(Array.isArray(symbols) ? { stock_count: symbols.length } : {}),
  };
}
