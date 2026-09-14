// GA4 이벤트 타입 정의 — 이벤트명 ↔ 파라미터 형태를 컴파일 타임에 결속한다.
//
// ⚠️ 개인정보 금지: 이메일·이름·전화번호·계좌 정보·보유 종목·투자 금액·개인 투자
// 기록은 어떤 파라미터로도 보내지 않는다. 허용 범위는 전략 종류·시장 종류·
// 리밸런싱 주기·백테스트 기간·구독 플랜명 같은 비식별 메타데이터뿐이다.

/** 가입·로그인 수단. apple은 아직 미배선(향후 OAuth 추가 대비 타입만 선언). guest는 /guest 테스터 입장. */
export type AuthMethod = "email" | "google" | "apple" | "guest";

export interface BacktestRunParams {
  /** 실행 시점 전략은 무명일 수 있다 — 무명이면 "unnamed" */
  strategy_name: string;
  /** "KOSPI" | "KOSDAQ" | "NASDAQ" | "NYSE" 또는 SP500처럼 거래소로 접히지 않는 유니버스 id 대문자 */
  market: string;
  /** "monthly" | "quarterly" | ... | "none" */
  rebalance_period: string;
  /** "5Y" 같은 상대 기간 또는 "2020-01-01~2024-12-31" 명시 창 */
  backtest_period: string;
  stock_count?: number;
}

export interface StrategySaveParams {
  strategy_name: string;
  strategy_type?: string;
}

export interface PricingViewParams {
  source?: string;
}

export interface PurchaseParams {
  transaction_id: string;
  value: number;
  currency: "KRW";
  plan_name: string;
}

export interface SubscriptionStartParams {
  plan_name: string;
  billing_period: "monthly" | "yearly";
  value: number;
  /** KR(토스)=KRW, US(PayPal)=USD — value 단위 구분용 */
  currency?: "KRW" | "USD";
}

/** 이벤트명 → 파라미터 매핑. trackEvent가 이 맵으로 타입을 강제한다. */
export interface AnalyticsEventMap {
  sign_up: { method: AuthMethod };
  login: { method: AuthMethod };
  backtest_run: BacktestRunParams;
  strategy_save: StrategySaveParams;
  pricing_view: PricingViewParams;
  purchase: PurchaseParams;
  subscription_start: SubscriptionStartParams;
}

export type AnalyticsEventName = keyof AnalyticsEventMap;
