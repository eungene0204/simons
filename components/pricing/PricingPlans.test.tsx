import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PricingPlans from "./PricingPlans";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}));

describe("PricingPlans", () => {
  it("renders equal-height pricing cards and unified subscription buttons", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getByTestId("pricing-plan-grid")).toHaveClass("items-stretch");
    expect(screen.getByTestId("pricing-plan-card-FREE")).toHaveClass("h-full");
    expect(screen.getByTestId("pricing-plan-card-PRO")).toHaveClass("h-full");
    expect(screen.getByTestId("pricing-plan-card-PREMIUM")).toHaveClass("h-full");
    expect(screen.getByTestId("pricing-plan-card-FREE")).toHaveClass(
      "transition-transform",
      "hover:-translate-y-1.5"
    );

    const subscriptionButtons = screen.getAllByRole("button", {
      name: "구독 시작하기",
    });

    expect(subscriptionButtons).toHaveLength(2);
    subscriptionButtons.forEach((button) => {
      expect(button).toHaveClass("border", "border-white/[0.12]", "text-white");
      expect(button).not.toHaveClass("bg-white", "text-black");
    });
  });

  it("uses the updated premium plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("여러 전략을 동시에 연구하고 검증하는 플랜")
    ).toBeInTheDocument();
    expect(
      screen.queryByText("여러 전략을 동시에 연구하고 고급 시뮬레이션을 운영하는 플랜")
    ).not.toBeInTheDocument();
  });

  it("uses the updated pro plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("전략을 본격적으로 만들고 검증하는 플랜")
    ).toBeInTheDocument();
    expect(
      screen.queryByText("전략을 본격적으로 만들고 검증하는 개인 투자자용 플랜")
    ).not.toBeInTheDocument();
  });

  it("renders initial simulated investment amounts in compact Korean units", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getByText("계좌당 초기 모의 투자금 천 만원")).toBeInTheDocument();
    expect(screen.getByText("계좌당 초기 모의 투자금 5천 만원")).toBeInTheDocument();
    expect(screen.getByText("계좌당 초기 모의 투자금 1억원")).toBeInTheDocument();
    expect(screen.queryByText(/₩10,000,000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/₩50,000,000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/₩100,000,000/)).not.toBeInTheDocument();
  });

  it("renders virtual account limits with maximum wording", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getByText("가상계좌 최대 1개")).toBeInTheDocument();
    expect(screen.getByText("가상계좌 최대 10개")).toBeInTheDocument();
    expect(screen.getByText("가상계좌 최대 30개")).toBeInTheDocument();
    expect(screen.queryByText("가상계좌 1개")).not.toBeInTheDocument();
    expect(screen.queryByText("가상계좌 10개")).not.toBeInTheDocument();
    expect(screen.queryByText("가상계좌 30개")).not.toBeInTheDocument();
  });

  it("renders VAT included copy next to each monthly price", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getAllByText("(VAT 포함)")).toHaveLength(3);
  });
});
