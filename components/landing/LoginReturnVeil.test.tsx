import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { isLoginReturn, LoginReturnVeil } from "./LoginReturnVeil";

afterEach(() => window.history.replaceState({}, "", "/"));

describe("isLoginReturn", () => {
  it("recognises the OAuth return (token in the hash, or a code in the query)", () => {
    expect(isLoginReturn("#access_token=abc&token_type=bearer", "")).toBe(true);
    expect(isLoginReturn("#foo=1&access_token=abc", "")).toBe(true);
    expect(isLoginReturn("", "?code=xyz")).toBe(true);
  });

  it("does not trigger on an ordinary visit", () => {
    expect(isLoginReturn("", "")).toBe(false);
    expect(isLoginReturn("#how-it-works", "?utm_source=x")).toBe(false);
  });
});

describe("LoginReturnVeil", () => {
  it("covers the page with a 'logging in' screen only while returning from Google", () => {
    window.history.replaceState({}, "", "/#access_token=abc");
    render(<LoginReturnVeil />);
    expect(screen.getByTestId("login-return-veil")).toHaveTextContent("로그인 중입니다");
    expect(screen.getByTestId("login-return-spinner")).toBeInTheDocument();
  });

  it("renders nothing on an ordinary visit", () => {
    render(<LoginReturnVeil />);
    expect(screen.queryByTestId("login-return-veil")).not.toBeInTheDocument();
  });
});
