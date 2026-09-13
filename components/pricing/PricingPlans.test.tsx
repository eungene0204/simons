import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PLANS } from "@/lib/plans";
import PricingPlans from "./PricingPlans";

const routerPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
    push: (...args: unknown[]) => routerPush(...args),
  }),
}));

// 결제 모달이 마운트 시 로드하는 토스페이먼츠 SDK를 목킹한다.
vi.mock("@tosspayments/tosspayments-sdk", () => ({
  loadTossPayments: vi.fn(async () => ({
    payment: () => ({ requestBillingAuth: vi.fn() }),
  })),
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
      // 구독 시작 CTA는 §10 주요 버튼(강조색 채움) 하나로 통일 — 흰 채움·회색 외곽선 아님
      expect(button).toHaveClass("bg-[var(--chat-accent)]", "text-[var(--chat-accent-ink)]", "rounded-xl");
      expect(button).not.toHaveClass("bg-white", "text-black", "border-white/[0.12]");
    });
  });

  it("모든 카드에서 월 백테스트 횟수를 첫 번째 항목으로 보여준다(FREE는 50회)", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    for (const [planId, label] of [
      ["FREE", "월 백테스트 50회"],
      ["PRO", "월 백테스트 500회"],
      ["PREMIUM", "월 백테스트 1,000회"],
    ] as const) {
      const items = within(screen.getByTestId(`pricing-plan-card-${planId}`)).getAllByRole(
        "listitem"
      );
      expect(items[0]).toHaveTextContent(label);
    }
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
      within(premiumCard).getByText("몬테카를로(Monte Carlo Simulation) 검증")
    ).toBeInTheDocument();
    expect(screen.getAllByText("워크포워드(walk-forward) 검증")).toHaveLength(3);
    const monteCarloLabels = screen.getAllByText("몬테카를로(Monte Carlo Simulation) 검증");
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

    expect(within(freeCard).getByText("AI 리포트")).toHaveClass("text-[var(--text-label)]");
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

  it("유료 플랜 선택 시 페이지 이동 없이 토스페이먼츠 결제 모달을 연다", async () => {
    // 모달이 마운트되며 주문 생성 요청을 보낸다 — 응답은 무시(모달 UI는 즉시 렌더)
    const fetchSpy = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchSpy);
    render(<PricingPlans currentPlanId="FREE" />);

    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    fireEvent.click(within(proCard).getByRole("button", { name: "구독 시작하기" }));

    // 페이지 이동이 아니라 모달이 뜬다 (findBy로 마운트 시 비동기 상태 갱신까지 정착)
    const modal = await screen.findByRole("dialog");
    expect(routerPush).not.toHaveBeenCalled();
    expect(within(modal).getByText("Pro 플랜 구독 결제")).toBeInTheDocument();
    expect(within(modal).getByRole("button", { name: "취소" })).toBeInTheDocument();
    expect(within(modal).getByRole("button", { name: "결제하기" })).toBeInTheDocument();
    // 결제 모달은 주문 생성 API(/api/payment/order)를 호출한다
    expect(fetchSpy).toHaveBeenCalledWith("/api/payment/order", expect.anything());
    vi.unstubAllGlobals();
  });

  it("highlights the current plan's icon in the accent color", () => {
    render(<PricingPlans currentPlanId="PRO" />);

    const currentCard = screen.getByTestId("pricing-plan-card-PRO");
    const currentIconWrapper = currentCard.querySelector("svg")?.parentElement;
    expect(currentIconWrapper).toHaveClass("text-[var(--chat-accent)]");

    const otherCard = screen.getByTestId("pricing-plan-card-FREE");
    const otherIconWrapper = otherCard.querySelector("svg")?.parentElement;
    expect(otherIconWrapper).toHaveClass("text-white");
    expect(otherIconWrapper).not.toHaveClass("text-[var(--chat-accent)]");
  });

  it("자동갱신 구독 중이면 현재 플랜 카드에 다음 결제일만 보여준다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: false }}
      />
    );

    const status = screen.getByTestId("subscription-renewal-status");
    expect(status).toHaveTextContent("다음 결제일");
    expect(within(status).queryByRole("button", { name: "자동갱신 해지" })).toBeNull();
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

  it("연간 결제 탭은 연 금액·월 환산·할인율을 보여준다", () => {
    render(<PricingPlans currentPlanId="FREE" />);

    fireEvent.click(screen.getByRole("button", { name: "연간 결제 · 20% 할인" }));

    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    expect(within(proCard).getByText("₩240,000")).toBeInTheDocument();
    expect(within(proCard).getByText("월 ₩20,000 꼴 · 20% 할인")).toBeInTheDocument();
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");
    expect(within(premiumCard).getByText("₩470,000")).toBeInTheDocument();
    // 무료 플랜은 주기 개념이 없다 — 어느 탭에서도 월 ₩0 그대로다
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByText("₩0")).toBeInTheDocument();
    expect(within(freeCard).getByText("/ 월")).toBeInTheDocument();
  });

  it("월간 구독자가 연간 탭을 열면 같은 플랜도 '연간 결제로 전환'으로 결제할 수 있다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ cycle: "monthly", nextBillingAt: "2026-10-03T00:00:00.000Z", canceled: false }}
      />
    );

    const proCard = screen.getByTestId("pricing-plan-card-PRO");
    expect(within(proCard).getByRole("button", { name: "현재 이용 중" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "연간 결제 · 20% 할인" }));
    expect(within(proCard).getByRole("button", { name: "연간 결제로 전환" })).toBeEnabled();

    // 회귀: 버튼은 눌리는데 아무 일도 일어나지 않던 결함 — 클릭 차단이 주기를 보지 않아
    // 같은 플랜이면 결제 모달을 열기 전에 빠져나갔다.
    fireEvent.click(within(proCard).getByRole("button", { name: "연간 결제로 전환" }));
    expect(screen.getByRole("dialog", { name: "Pro 플랜 구독 결제" })).toBeInTheDocument();
  });

  it("연간 구독 중에는 유료 플랜 변경을 잠그고 해지만 남긴다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ cycle: "yearly", nextBillingAt: "2027-09-13T00:00:00.000Z", canceled: false }}
      />
    );

    expect(screen.getByTestId("yearly-lock-notice")).toBeInTheDocument();
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");
    expect(within(premiumCard).getByRole("button", { name: "구독 시작하기" })).toBeDisabled();
    // 월간 탭으로 돌아가도 잠금은 유지된다(주기만 바꿔 우회 불가)
    fireEvent.click(screen.getByRole("button", { name: "월간 결제" }));
    expect(within(premiumCard).getByRole("button", { name: "구독 시작하기" })).toBeDisabled();
    // 해지는 언제든 가능해야 한다
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByRole("button", { name: "구독 해지" })).toBeEnabled();
  });

  it("연간 구독자는 요금제 페이지를 열면 연간 탭이 선택돼 있다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ cycle: "yearly", nextBillingAt: "2027-09-13T00:00:00.000Z", canceled: false }}
      />
    );

    expect(screen.getByRole("button", { name: "연간 결제 · 20% 할인" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(
      within(screen.getByTestId("pricing-plan-card-PRO")).getByRole("button", {
        name: "현재 이용 중",
      })
    ).toBeDisabled();
  });

  it("자동갱신 구독 중이면 FREE 카드 버튼은 '구독 해지'다(즉시 전환이 아니라 해지 예약)", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: false }}
      />
    );
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByRole("button", { name: "구독 해지" })).toBeEnabled();
    expect(within(freeCard).queryByRole("button", { name: "무료로 전환" })).toBeNull();
  });

  it("해지 예약된 구독은 FREE 카드 버튼을 '해지 예약됨'으로 비활성화한다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{ nextBillingAt: "2026-08-10T00:00:00.000Z", canceled: true }}
      />
    );
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByRole("button", { name: "해지 예약됨" })).toBeDisabled();
  });

  it("구독 없는 유료 등급은 FREE 카드 버튼이 '무료로 전환'(즉시)이다", () => {
    render(<PricingPlans currentPlanId="PRO" />);
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByRole("button", { name: "무료로 전환" })).toBeEnabled();
  });

  it("서버가 넘긴 플랜 정의(관리자 한도 오버라이드)를 카드에 그대로 반영한다", () => {
    const plans = {
      ...PLANS,
      FREE: { ...PLANS.FREE, monthlyBacktestLimit: 50, maxVirtualAccounts: 2 },
    };
    render(<PricingPlans currentPlanId="FREE" plans={plans} />);
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByText("월 백테스트 50회")).toBeInTheDocument();
    expect(within(freeCard).getByText("시뮬레이션 가상계좌 2개")).toBeInTheDocument();
  });

  it("PayPal 구독자는 유료 결제 버튼이 잠기고 글로벌 요금제 안내가 뜬다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{
          provider: "paypal",
          nextBillingAt: "2026-10-10T00:00:00.000Z",
          canceled: false,
        }}
      />
    );

    expect(screen.getByTestId("paypal-managed-notice")).toBeInTheDocument();
    const premiumCard = screen.getByTestId("pricing-plan-card-PREMIUM");
    expect(within(premiumCard).getByRole("button", { name: "구독 시작하기" })).toBeDisabled();
    // 주기 탭을 바꿔도 우회할 수 없다
    fireEvent.click(screen.getByRole("button", { name: "연간 결제 · 20% 할인" }));
    expect(within(premiumCard).getByRole("button", { name: "구독 시작하기" })).toBeDisabled();
    // 해지는 서버가 결제 수단(PSP)을 분기하므로(subscriptionCancel.ts) 여기서도 열어 둔다
    const freeCard = screen.getByTestId("pricing-plan-card-FREE");
    expect(within(freeCard).getByRole("button", { name: "구독 해지" })).toBeEnabled();
  });

  it("토스 구독자에게는 PayPal 안내를 렌더링하지 않는다", () => {
    render(
      <PricingPlans
        currentPlanId="PRO"
        subscription={{
          provider: "toss",
          nextBillingAt: "2026-10-10T00:00:00.000Z",
          canceled: false,
        }}
      />
    );
    expect(screen.queryByTestId("paypal-managed-notice")).toBeNull();
  });

  it("구독 정보가 없으면(FREE) 갱신 상태 UI를 렌더링하지 않는다", () => {
    render(<PricingPlans currentPlanId="FREE" />);
    expect(screen.queryByTestId("subscription-renewal-status")).toBeNull();
  });
});
