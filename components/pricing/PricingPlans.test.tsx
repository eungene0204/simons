import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PricingPlans from "./PricingPlans";

const routerPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
    push: (...args: unknown[]) => routerPush(...args),
  }),
}));

beforeEach(() => {
  routerPush.mockClear();
});

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
    expect(within(freeCard).getAllByRole("listitem")).toHaveLength(8);
    expect(within(proCard).getAllByRole("listitem")).toHaveLength(8);
    expect(within(premiumCard).getAllByRole("listitem")).toHaveLength(8);

    const subscriptionButtons = screen.getAllByRole("button", {
      name: "구독 시작하기",
    });

    expect(subscriptionButtons).toHaveLength(2);
    subscriptionButtons.forEach((button) => {
      expect(button).toHaveClass("border", "border-white/[0.12]", "text-white");
      expect(button).not.toHaveClass("bg-white", "text-black");
    });
  });

  it("uses the updated free plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("처음 전략을 만들고 백테스트를 경험해 보세요")
    ).toBeInTheDocument();
  });

  it("uses the updated premium plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("전문가 수준으로 전략을 연구하고 검증 해보세요")
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

  it("shows AI report only for pro and premium plans", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");

    expect(within(freeCard).getByText("AI 리포트")).toHaveClass("text-gray-600");
    expect(within(proCard).getByText("AI 리포트")).toHaveClass("text-gray-200");
    expect(within(premiumCard).getByText("AI 리포트")).toHaveClass("text-gray-200");
  });

  it("uses the updated pro plan description", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    expect(
      screen.getByText("여러 전략을 동시에 연구하고 시뮬레이션 해보세요")
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

  it("유료 플랜 선택 시 결제 API 대신 토스페이먼츠 체크아웃으로 이동한다", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<PricingPlans currentPlanId="FREE" />);

    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    fireEvent.click(within(proCard).getByRole("button", { name: "구독 시작하기" }));

    expect(routerPush).toHaveBeenCalledWith("/pricing/checkout?plan=PRO");
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
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

  it("자동갱신 구독 중이면 현재 플랜 카드에 다음 결제일과 해지 버튼을 보여준다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: false }}
      />
    );

    const status = screen.getByTestId("subscription-renewal-status");
    expect(status).toHaveTextContent("다음 결제일");
    expect(within(status).getByRole("button", { name: "자동갱신 해지" })).toBeInTheDocument();
  });

  it("해지 버튼 클릭 시 확인 후 해지 API를 호출한다", () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchSpy);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: false }}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "자동갱신 해지" }));

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/payment/billing/cancel",
      expect.objectContaining({ method: "POST" })
    );

    confirmSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("해지 예약된 구독은 만료 안내만 보여주고 해지 버튼을 숨긴다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: true }}
      />
    );

    const status = screen.getByTestId("subscription-renewal-status");
    expect(status).toHaveTextContent("해지 예약됨");
    expect(within(status).queryByRole("button", { name: "자동갱신 해지" })).toBeNull();
  });

  it("구독 정보가 없으면(FREE) 갱신 상태 UI를 렌더링하지 않는다", () => {
    render(<PricingPlans currentPlanId="FREE" />);
    expect(screen.queryByTestId("subscription-renewal-status")).toBeNull();
  });
});
