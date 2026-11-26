import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BillingFailureBanner from "./BillingFailureBanner";

const FAILURE = { planName: "Pro", failCount: 2, maxFailCount: 3, nextRetryAt: "2026-12-02T01:00:00.000Z" };

describe("BillingFailureBanner", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("실패 상태면 횟수와 고객센터 연락처를 보여 준다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ failure: FAILURE }) }));
    render(<BillingFailureBanner />);
    const banner = await screen.findByTestId("billing-failure-banner");
    expect(banner.textContent).toContain("(2/3)");
    expect(banner.textContent).toContain("support@nullstock.im");
  });

  it("실패 상태가 아니면 아무것도 그리지 않는다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ failure: null }) });
    vi.stubGlobal("fetch", fetchMock);
    render(<BillingFailureBanner />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("billing-failure-banner")).toBeNull();
  });

  it("닫으면 이 탭에서는 다시 조회하지 않는다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ failure: FAILURE }) });
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<BillingFailureBanner />);
    fireEvent.click(await screen.findByRole("button"));
    expect(screen.queryByTestId("billing-failure-banner")).toBeNull();
    unmount();
    render(<BillingFailureBanner />);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
