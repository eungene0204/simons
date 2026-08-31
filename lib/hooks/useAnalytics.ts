"use client";

// GA4 이벤트 훅 — 컴포넌트에서 이벤트별 메서드로 호출한다.
// 반환 객체는 메모이즈되어 useEffect 의존성에 안전하게 넣을 수 있다.

import { useMemo } from "react";
import {
  trackEvent,
  type AuthMethod,
  type BacktestRunParams,
  type PricingViewParams,
  type PurchaseParams,
  type StrategySaveParams,
  type SubscriptionStartParams,
} from "@/lib/analytics";

export function useAnalytics() {
  return useMemo(
    () => ({
      signUp: (method: AuthMethod) => trackEvent("sign_up", { method }),
      login: (method: AuthMethod) => trackEvent("login", { method }),
      backtestRun: (params: BacktestRunParams) => trackEvent("backtest_run", params),
      strategySave: (params: StrategySaveParams) => trackEvent("strategy_save", params),
      pricingView: (params: PricingViewParams = {}) => trackEvent("pricing_view", params),
      purchase: (params: PurchaseParams) => trackEvent("purchase", params),
      subscriptionStart: (params: SubscriptionStartParams) => trackEvent("subscription_start", params),
    }),
    []
  );
}
