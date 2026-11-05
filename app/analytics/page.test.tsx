import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";

vi.mock("./new/page", () => ({
  default: () => <div>전략 만들기 페이지</div>,
}));

const sessionUserId = vi.hoisted(() => ({ current: null as number | null }));
vi.mock("@/lib/get-user", () => ({
  getSessionUserId: async () => sessionUserId.current,
}));

const requestRegion = vi.hoisted(() => ({ current: "kr" as "kr" | "us" }));
vi.mock("@/lib/geo/server", () => ({
  getRequestRegion: () => requestRegion.current,
}));

const redirect = vi.hoisted(() =>
  vi.fn((href: string) => {
    throw new Error(`NEXT_REDIRECT:${href}`);
  })
);
vi.mock("next/navigation", () => ({ redirect }));

afterEach(() => {
  sessionUserId.current = null;
  requestRegion.current = "kr";
  redirect.mockClear();
});

describe("StrategyLabPage", () => {
  it("renders the strategy creation page for a signed-in user", async () => {
    sessionUserId.current = 7;

    render(await StrategyLabPage());

    expect(screen.getByText("전략 만들기 페이지")).toBeInTheDocument();
    expect(redirect).not.toHaveBeenCalled();
  });

  // 회귀: 비로그인 방문자에게 전략연구소를 잠깐 그렸다가 클라이언트 가드가 홈으로 튕기던 문제.
  it("redirects an anonymous visitor to the home landing on the server", async () => {
    await expect(StrategyLabPage()).rejects.toThrow("NEXT_REDIRECT:/");
    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("keeps the region prefix when redirecting an anonymous visitor", async () => {
    requestRegion.current = "us";

    await expect(StrategyLabPage()).rejects.toThrow("NEXT_REDIRECT:/us");
    expect(redirect).toHaveBeenCalledWith("/us");
  });
});
