import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getSessionMock = vi.fn();
vi.mock("@/lib/firebase", () => ({
  getSupabaseBrowserClient: () => ({ auth: { getSession: getSessionMock } }),
}));

import { accessTokenFromHash, completeLoginReturn, isLoginReturn } from "../loginReturn";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

const okLogin = () =>
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({ user: { name: "테스터", email: "t@example.com" } }) });

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

describe("accessTokenFromHash", () => {
  it("reads the access token out of the implicit-flow hash", () => {
    expect(accessTokenFromHash("#access_token=abc&refresh_token=r&token_type=bearer")).toBe("abc");
    expect(accessTokenFromHash("#how-it-works")).toBeNull();
  });
});

describe("completeLoginReturn", () => {
  // 회귀: 예전엔 Supabase 클라이언트의 해시 처리(토큰 확인 왕복)와 `/api/user`를 거친 뒤에야 `/api/login`을 불렀다.
  it("sends the hash token straight to /api/login without a Supabase round trip", async () => {
    okLogin();
    window.history.replaceState({}, "", "/#access_token=token-1&token_type=bearer");

    await expect(completeLoginReturn()).resolves.toEqual({ name: "테스터", email: "t@example.com" });

    expect(getSessionMock).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/login",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ supabaseAccessToken: "token-1" }) })
    );
    expect(window.location.hash).toBe("");
  });

  it("shares one exchange between callers that start together", async () => {
    okLogin();
    window.history.replaceState({}, "", "/#access_token=token-2");

    const [a, b] = await Promise.all([completeLoginReturn(), completeLoginReturn()]);

    expect(a).toEqual(b);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("resolves null when the server rejects the token", async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({ error: "Google 로그인 검증에 실패했습니다." }) });
    window.history.replaceState({}, "", "/#access_token=token-3");

    await expect(completeLoginReturn()).resolves.toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("falls back to the Supabase code exchange when the token is not in the hash", async () => {
    okLogin();
    getSessionMock.mockResolvedValue({ data: { session: { access_token: "from-code" } } });
    window.history.replaceState({}, "", "/?code=xyz");

    await completeLoginReturn();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/login",
      expect.objectContaining({ body: JSON.stringify({ supabaseAccessToken: "from-code" }) })
    );
  });
});
