import { render, screen, within } from "@testing-library/react";
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
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");

    expect(freeCard).toHaveClass("h-full");
    expect(proCard).toHaveClass("h-full");
    expect(premiumCard).toHaveClass("h-full");
    expect(freeCard).toHaveClass(
      "px-8",
      "py-10",
      "transition-transform",
      "hover:-translate-y-1.5"
    );
    expect(within(freeCard).getAllByRole("listitem")).toHaveLength(6);
    expect(within(proCard).getAllByRole("listitem")).toHaveLength(6);
    expect(within(premiumCard).getAllByRole("listitem")).toHaveLength(6);

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

  it("renders premium validation features in aligned rows across all cards", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");

    expect(within(premiumCard).getByText("워크포워드(walk-forward) 검증")).toBeInTheDocument();
    expect(
      within(premiumCard).getByText("몬테 카를로(Monte Carlo Simulation) 검증")
    ).toBeInTheDocument();
    expect(screen.getAllByText("워크포워드(walk-forward) 검증")).toHaveLength(3);
    const monteCarloLabels = screen.getAllByText("몬테 카를로(Monte Carlo Simulation) 검증");
    expect(monteCarloLabels).toHaveLength(3);
    monteCarloLabels.forEach((label) => {
      expect(label).toHaveClass("xl:whitespace-nowrap");
    });
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
