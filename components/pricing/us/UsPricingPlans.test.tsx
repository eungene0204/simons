import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import UsPricingPlans from "./UsPricingPlans";

describe("UsPricingPlans", () => {
  // 글로벌 요금제 카드는 한국 카드(components/pricing/PricingPlans)와 같은 형태여야 한다.
  it("한국 카드와 동일한 레이아웃·기능 행 수로 렌더한다", () => {
    render(<UsPricingPlans currentPlanId="FREE" />);

    expect(screen.getByTestId("pricing-plan-grid")).toHaveClass("items-stretch");
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");

    for (const card of [freeCard, proCard, premiumCard]) {
      expect(card).toHaveClass(
        "h-full",
        "px-8",
        "py-10",
        "transition-transform",
        "hover:-translate-y-1.5"
      );
      expect(within(card).getAllByRole("listitem")).toHaveLength(8);
    }
  });

  it("가격을 USD로 표시한다", () => {
    render(<UsPricingPlans currentPlanId="FREE" />);

    expect(within(screen.getByTestId("pricing-plan-card-FREE")).getByText("$0")).toBeTruthy();
    expect(within(screen.getByTestId("pricing-plan-card-PRO")).getByText("$19")).toBeTruthy();
    expect(within(screen.getByTestId("pricing-plan-card-PREMIUM")).getByText("$39")).toBeTruthy();
    expect(screen.getAllByText("/ month")).toHaveLength(3);
  });

  it("결제 배선 전까지 유료 CTA는 비활성 안내로 둔다", () => {
    render(<UsPricingPlans currentPlanId="FREE" />);

    const current = within(screen.getByTestId("pricing-plan-card-FREE")).getByRole("button");
    expect(current).toHaveTextContent("Current plan");
    for (const planId of ["PRO", "PREMIUM"]) {
      const cta = within(screen.getByTestId(`pricing-plan-card-${planId}`)).getByRole("button");
      expect(cta).toHaveTextContent("Coming soon");
      expect(cta).toBeDisabled();
    }
  });
  // 회귀: phosphor-react가 createContext를 쓰므로 RSC에서 임포트하면 렌더가 터진다
  // (2026-08-25 — /us/pricing 서버 에러). jsdom 렌더는 양쪽 다 통과하므로 소스로 확인한다.
  it("phosphor 아이콘을 쓰므로 클라이언트 컴포넌트여야 한다", () => {
    const source = readFileSync(join(__dirname, "UsPricingPlans.tsx"), "utf-8");
    expect(source.trimStart().startsWith('"use client";')).toBe(true);
  });
});
