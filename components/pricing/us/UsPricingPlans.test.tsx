import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UsPricingPlans from "./UsPricingPlans";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: () => refresh() }),
  usePathname: () => "/us/pricing",
}));

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

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

  it("PayPal이 설정되지 않은 환경에서는 유료 CTA를 열지 않는다", () => {
    render(<UsPricingPlans currentPlanId="FREE" paypalEnabled={false} />);

    const current = within(screen.getByTestId("pricing-plan-card-FREE")).getByRole("button");
    expect(current).toHaveTextContent("Current plan");
    for (const planId of ["PRO", "PREMIUM"]) {
      const cta = within(screen.getByTestId(`pricing-plan-card-${planId}`)).getByRole("button");
      expect(cta).toHaveTextContent("Coming soon");
      expect(cta).toBeDisabled();
    }
  });

  it("유료 CTA는 구독을 만들고 PayPal 승인 페이지로 보낸다", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { subscriptionId: "I-SUB-1", approveUrl: "https://paypal.com/approve/1" })
    );
    // jsdom은 location 대입을 막으므로 대체 가능한 객체로 바꿔 이동을 관찰한다
    // pathname까지 넣어야 지역 헤더가 경로에서 파생된다(실제 /us 탭과 같은 조건)
    const location = { href: "", pathname: "/us/pricing" };
    Object.defineProperty(window, "location", { value: location, writable: true });

    render(<UsPricingPlans currentPlanId="FREE" paypalEnabled />);
    fireEvent.click(within(screen.getByTestId("pricing-plan-card-PRO")).getByRole("button"));

    await waitFor(() => expect(location.href).toBe("https://paypal.com/approve/1"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/payment/paypal/subscription");
    expect(JSON.parse(init.body)).toEqual({ planId: "PRO" });
    // 지역 헤더가 빠지면 /us 탭의 호출이 KR로 오염된다
    expect(init.headers).toMatchObject({ "x-nullstock-region": "us" });
  });

  it("구독 생성이 실패하면 승인 페이지로 보내지 않고 오류를 보여준다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(409, { error: "Subscription already in progress." }));

    render(<UsPricingPlans currentPlanId="FREE" paypalEnabled />);
    fireEvent.click(within(screen.getByTestId("pricing-plan-card-PREMIUM")).getByRole("button"));

    await waitFor(() =>
      expect(screen.getByTestId("us-pricing-error")).toHaveTextContent(
        "Subscription already in progress."
      )
    );
  });

  it("구독 중이면 FREE 카드가 해지 버튼이 되고, 해지 예약 뒤에는 다시 누를 수 없다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { ok: true, expiresAt: null }));

    const { rerender } = render(
      <UsPricingPlans
        currentPlanId="PRO"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: false }}
      />
    );

    const freeCta = within(screen.getByTestId("pricing-plan-card-FREE")).getByRole("button");
    expect(freeCta).toHaveTextContent("Cancel subscription");
    fireEvent.click(freeCta);

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/payment/paypal/subscription/cancel");

    rerender(
      <UsPricingPlans
        currentPlanId="PRO"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: true }}
      />
    );
    const canceledCta = within(screen.getByTestId("pricing-plan-card-FREE")).getByRole("button");
    expect(canceledCta).toHaveTextContent("Cancellation scheduled");
    expect(canceledCta).toBeDisabled();
  });

  it("구독 중이면 다른 유료 카드가 플랜 변경 버튼이 되고 revise 경로를 부른다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { approveUrl: "https://paypal.com/revise/1" }));
    const location = { href: "", pathname: "/us/pricing" };
    Object.defineProperty(window, "location", { value: location, writable: true });

    render(
      <UsPricingPlans
        currentPlanId="PREMIUM"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: false }}
      />
    );

    const proCta = within(screen.getByTestId("pricing-plan-card-PRO")).getByRole("button");
    expect(proCta).toHaveTextContent("Change plan");
    fireEvent.click(proCta);

    await waitFor(() => expect(location.href).toBe("https://paypal.com/revise/1"));
    // 새 구독 생성이 아니라 변경(revise) 라우트여야 한다 — 겹쳐 만들면 이중 청구다
    expect(fetchMock.mock.calls[0][0]).toBe("/api/payment/paypal/subscription/change");
  });

  it("플랜 변경이 예약되면 대상 카드가 잠기고 현재 카드에 전환 예정을 표시한다", () => {
    render(
      <UsPricingPlans
        currentPlanId="PREMIUM"
        paypalEnabled
        subscription={{
          nextBillingAt: "2026-09-30T00:00:00Z",
          canceled: false,
          pendingPlanId: "PRO",
        }}
      />
    );

    const proCta = within(screen.getByTestId("pricing-plan-card-PRO")).getByRole("button");
    expect(proCta).toHaveTextContent("Scheduled for September 30, 2026");
    expect(proCta).toBeDisabled();
    expect(screen.getByTestId("subscription-renewal-status")).toHaveTextContent(
      "Changes to Pro on September 30, 2026"
    );
  });

  it("해지 예약 중에는 다른 유료 카드도 잠긴다(만료 후 재구독)", () => {
    render(
      <UsPricingPlans
        currentPlanId="PREMIUM"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: true }}
      />
    );

    const proCta = within(screen.getByTestId("pricing-plan-card-PRO")).getByRole("button");
    expect(proCta).toHaveTextContent("Available after expiry");
    expect(proCta).toBeDisabled();
  });

  it("이용 중인 유료 플랜에 다음 결제일·해지 예약 상태를 표시한다", () => {
    const { rerender } = render(
      <UsPricingPlans
        currentPlanId="PRO"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: false }}
      />
    );
    expect(screen.getByTestId("subscription-renewal-status")).toHaveTextContent(
      "Next billing date: September 30, 2026"
    );

    rerender(
      <UsPricingPlans
        currentPlanId="PRO"
        paypalEnabled
        subscription={{ nextBillingAt: "2026-09-30T00:00:00Z", canceled: true }}
      />
    );
    expect(screen.getByTestId("subscription-renewal-status")).toHaveTextContent(
      "Canceled - access until September 30, 2026"
    );
  });
  // 회귀: phosphor-react가 createContext를 쓰므로 RSC에서 임포트하면 렌더가 터진다
  // (2026-08-25 — /us/pricing 서버 에러). jsdom 렌더는 양쪽 다 통과하므로 소스로 확인한다.
  it("phosphor 아이콘을 쓰므로 클라이언트 컴포넌트여야 한다", () => {
    const source = readFileSync(join(__dirname, "UsPricingPlans.tsx"), "utf-8");
    expect(source.trimStart().startsWith('"use client";')).toBe(true);
  });
});
