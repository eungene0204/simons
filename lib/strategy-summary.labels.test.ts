import { describe, expect, it } from "vitest";

import { METRIC_LABELS, REBAL_LABELS } from "./strategy-summary";

/** 백엔드 정본(backend/engine/nl_parser.py FundamentalFilter.metric Literal). 새 지표를 추가하면
 *  여기와 METRIC_LABELS를 함께 갱신한다 — 빠지면 요약 카드에 내부 식별자가 그대로 나간다
 *  (2026-09-15 실측: 'ocf_growth >= 10'). */
const BACKEND_FUNDAMENTAL_METRICS = [
  "per", "pbr", "psr", "pcr", "ev_ebitda", "ev_ebit", "roe_or_gpa", "roa", "debt_ratio",
  "current_ratio", "quick_ratio", "reserve_ratio", "net_margin", "gross_margin", "operating_margin",
  "revenue_growth", "operating_income_growth", "net_income_growth", "market_cap", "trading_value",
  "dividend_yield", "payout_rate", "dividend_growth", "eps_growth", "ebitda_growth", "ocf_growth",
  "fcf_growth", "eps", "ebit", "net_income", "owner_net_income", "operating_cf_amount",
  "investing_cf_amount", "financing_cf_amount",
];
const BACKEND_REBALANCING_PERIODS = ["none", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly"];

describe("백엔드 enum × 프론트 라벨 표 전수 대조 — 내부 식별자가 화면에 새지 않는다", () => {
  it("재무 지표 34개 전부 한국어(또는 공인 약어) 라벨이 있다", () => {
    for (const metric of BACKEND_FUNDAMENTAL_METRICS) {
      expect(METRIC_LABELS[metric], `라벨 누락: ${metric}`).toBeTruthy();
      // 라벨이 소문자 snake_case 식별자 그대로면 누락과 같다.
      expect(METRIC_LABELS[metric]).not.toMatch(/^[a-z_]+$/);
    }
  });

  it("리밸런싱 주기 7개 전부 한국어 라벨이 있다", () => {
    for (const period of BACKEND_REBALANCING_PERIODS) {
      expect(REBAL_LABELS[period], `라벨 누락: ${period}`).toBeTruthy();
      expect(REBAL_LABELS[period]).not.toMatch(/[a-z]/);
    }
  });
});
