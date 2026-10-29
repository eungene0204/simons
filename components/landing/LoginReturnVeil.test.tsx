import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginReturnVeil } from "./LoginReturnVeil";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("LoginReturnVeil", () => {
  it("covers the page with a 'logging in' screen only while returning from Google", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    window.history.replaceState({}, "", "/#access_token=pending");
    render(<LoginReturnVeil />);
    expect(screen.getByTestId("login-return-veil")).toHaveTextContent("로그인 중입니다");
    expect(screen.getByTestId("login-return-spinner")).toBeInTheDocument();
  });

  // 회귀: 교환이 실패해도 가림막을 걷는 길이 없어 스피너만 끝없이 돌았다.
  it("lifts the veil when the login exchange fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    window.history.replaceState({}, "", "/#access_token=rejected");
    render(<LoginReturnVeil />);
    await waitFor(() => expect(screen.queryByTestId("login-return-veil")).not.toBeInTheDocument());
  });

  it("renders nothing on an ordinary visit", () => {
    render(<LoginReturnVeil />);
    expect(screen.queryByTestId("login-return-veil")).not.toBeInTheDocument();
  });
});
