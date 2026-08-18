import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import LanguageToggle from "@/lib/i18n/LanguageToggle";
import { __resetLanguageForTests, getLanguage } from "@/lib/i18n";

afterEach(() => {
  __resetLanguageForTests();
  document.cookie = "nullstock.lang=; path=/; max-age=0";
  window.localStorage.removeItem("nullstock.lang");
  vi.restoreAllMocks();
});

function renderToggle(initial: "ko" | "en" = "ko") {
  return render(
    <LanguageProvider initialLanguage={initial}>
      <LanguageToggle />
    </LanguageProvider>,
  );
}

describe("LanguageToggle", () => {
  it("KR / EN 두 선택지를 보여주고 현재 언어를 눌린 상태로 표시한다", () => {
    renderToggle("ko");
    const kr = screen.getByRole("button", { name: "KR" });
    const en = screen.getByRole("button", { name: "EN" });
    expect(kr).toHaveAttribute("aria-pressed", "true");
    expect(en).toHaveAttribute("aria-pressed", "false");
  });

  it("EN을 누르면 언어를 영속(쿠키·localStorage)하고 새로고침한다", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload },
    });
    try {
      renderToggle("ko");
      fireEvent.click(screen.getByRole("button", { name: "EN" }));
      expect(document.cookie).toContain("nullstock.lang=en");
      expect(window.localStorage.getItem("nullstock.lang")).toBe("en");
      expect(getLanguage()).toBe("en");
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });

  it("이미 선택된 언어를 다시 눌러도 새로고침하지 않는다", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", { configurable: true, value: { ...original, reload } });
    try {
      renderToggle("en");
      fireEvent.click(screen.getByRole("button", { name: "EN" }));
      expect(reload).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });

  it("영어로 렌더되면 자식의 t() 표시가 영어다(SSR과 같은 언어로 그린다)", () => {
    // 실제 컴포넌트처럼 렌더 중에 언어를 읽는다(JSX 생성 시점이 아니라).
    const Child = () => <span data-testid="label">{getLanguage() === "en" ? "en" : "ko"}</span>;
    render(
      <LanguageProvider initialLanguage="en">
        <Child />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("label")).toHaveTextContent("en");
  });
});
