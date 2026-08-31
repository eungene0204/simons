import { afterEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { cleanup, render } from "@testing-library/react";
import PricingViewTracker from "./PricingViewTracker";

type GtagWindow = { gtag?: unknown };

afterEach(() => {
  cleanup();
  delete (window as GtagWindow).gtag;
});

describe("PricingViewTracker", () => {
  it("리렌더가 반복돼도 pricing_view는 방문당 1회만 보낸다", () => {
    const gtag = vi.fn();
    (window as GtagWindow).gtag = gtag;

    const { rerender } = render(<PricingViewTracker />);
    rerender(<PricingViewTracker />);
    rerender(<PricingViewTracker />);

    expect(gtag).toHaveBeenCalledTimes(1);
    expect(gtag).toHaveBeenCalledWith("event", "pricing_view", {});
  });

  it("StrictMode 이중 마운트에서도 1회만 보낸다", () => {
    const gtag = vi.fn();
    (window as GtagWindow).gtag = gtag;

    render(
      <StrictMode>
        <PricingViewTracker />
      </StrictMode>
    );

    expect(gtag).toHaveBeenCalledTimes(1);
  });

  it("source가 있으면 파라미터로 싣는다", () => {
    const gtag = vi.fn();
    (window as GtagWindow).gtag = gtag;

    render(<PricingViewTracker source="navbar" />);

    expect(gtag).toHaveBeenCalledWith("event", "pricing_view", { source: "navbar" });
  });
});
