import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OPEN_LOGIN_EVENT } from "@/lib/auth/loginEvents";
import { StartButton } from "./StartButton";

const renderButton = () =>
  render(
    <StartButton href="/analytics" className="btn">
      무료로 시작하기
    </StartButton>,
  );

afterEach(() => vi.restoreAllMocks());

describe("StartButton", () => {
  it("asks for the Google login modal and does not navigate when the navigation handled it", () => {
    const onRequest = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener(OPEN_LOGIN_EVENT, onRequest);
    try {
      renderButton();
      const notPrevented = fireEvent.click(screen.getByRole("link", { name: "무료로 시작하기" }));
      expect(onRequest).toHaveBeenCalledTimes(1);
      expect(notPrevented).toBe(false); // the link's own navigation was cancelled
    } finally {
      window.removeEventListener(OPEN_LOGIN_EVENT, onRequest);
    }
  });

  it("falls back to the link when nothing opens the modal", () => {
    renderButton();
    const link = screen.getByRole("link", { name: "무료로 시작하기" });
    expect(link).toHaveAttribute("href", "/analytics");
    expect(fireEvent.click(link)).toBe(true); // not cancelled: the browser follows the href
  });

  it("leaves modified clicks (new tab) to the browser", () => {
    const onRequest = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener(OPEN_LOGIN_EVENT, onRequest);
    try {
      renderButton();
      fireEvent.click(screen.getByRole("link", { name: "무료로 시작하기" }), { ctrlKey: true });
      expect(onRequest).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(OPEN_LOGIN_EVENT, onRequest);
    }
  });
});
