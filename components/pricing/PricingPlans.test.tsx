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
      screen.getByText("여러 전략을 동시에 연구하고 지속적으로 검증하는 플랜")
    ).toBeInTheDocument();
  });

  it("uses the updated pro plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("투자 전략을 꾸준히 연구하고 검증하는 플랜")
    ).toBeInTheDocument();
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

  it("renders virtual account limits with unified simulation wording", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getByText("시뮬레이션 가상계좌 1개")).toBeInTheDocument();
    expect(screen.getByText("시뮬레이션 가상계좌 10개")).toBeInTheDocument();
    expect(screen.getByText("시뮬레이션 가상계좌 30개")).toBeInTheDocument();
    expect(screen.queryByText(/가상계좌 최대/)).not.toBeInTheDocument();
    expect(screen.queryByText(/동시 시뮬레이션/)).not.toBeInTheDocument();
  });

  it("renders VAT included copy next to each monthly price", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(screen.getAllByText("(VAT 포함)")).toHaveLength(3);
  });

  it("highlights the current plan's icon in blue", () => {
    render(<PricingPlans currentPlanId="PRO" />);

    const currentCard = screen.getByTestId("pricing-plan-card-PRO");
    const currentIconWrapper = currentCard.querySelector("svg")?.parentElement;
    expect(currentIconWrapper).toHaveClass("text-blue-400");

    const otherCard = screen.getByTestId("pricing-plan-card-FREE");
    const otherIconWrapper = otherCard.querySelector("svg")?.parentElement;
    expect(otherIconWrapper).toHaveClass("text-white");
    expect(otherIconWrapper).not.toHaveClass("text-blue-400");
  });
});
