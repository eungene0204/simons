import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UsPaymentSuccess from "./UsPaymentSuccess";

vi.mock("next/navigation", () => ({ usePathname: () => "/us/pricing/success" }));

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

describe("UsPaymentSuccess", () => {
  it("활성 구독이면 적용된 플랜을 알린다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: "ACTIVE", planId: "PRO" }));

    render(<UsPaymentSuccess />);

    await waitFor(() => expect(screen.getByText("Subscription active")).toBeTruthy());
    expect(screen.getByText("Your PRO plan is now active.")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/payment/paypal/subscription/sync");
  });

  it("아직 활성 전이면 실패가 아니라 처리 중으로 안내한다(승격 정본은 웹훅이다)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: "APPROVAL_PENDING", planId: "FREE" }));

    render(<UsPaymentSuccess />);

    await waitFor(() =>
      expect(screen.getByText("Subscription is being processed")).toBeTruthy()
    );
  });

  it("확인에 실패하면 오류 메시지를 그대로 보여준다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { error: "구독 정보를 찾을 수 없습니다." }));

    render(<UsPaymentSuccess />);

    await waitFor(() =>
      expect(screen.getByText("We could not confirm your subscription")).toBeTruthy()
    );
    expect(screen.getByText("구독 정보를 찾을 수 없습니다.")).toBeTruthy();
  });

  it("StrictMode 이중 실행에도 동기화 요청은 한 번만 나간다", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: "ACTIVE", planId: "PRO" }));
    const { rerender } = render(<UsPaymentSuccess />);
    rerender(<UsPaymentSuccess />);

    await waitFor(() => expect(screen.getByText("Subscription active")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
