// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// 게스트 입장 링크 — `/guest#<입장 코드>`로 들어오면 코드를 주소창에서 지우고 POST 본문으로만 보낸다.

vi.mock("@/components/layout/NullstockLogoMark", () => ({ default: () => null }));
vi.mock("@/lib/geo/useRegion", () => ({ useRegionHref: () => (path: string) => path }));
vi.mock("@/lib/hooks/useAnalytics", () => ({ useAnalytics: () => ({ login: vi.fn() }) }));

import GuestLoginForm from "./GuestLoginForm";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("GuestLoginForm 입장 링크", () => {
  it("hash의 코드를 지운 뒤 invite로 POST한다", async () => {
    window.history.replaceState(null, "", "/guest#guest_1234.secretvalue");
    fetchMock.mockReturnValue(new Promise(() => {})); // 응답 대기 상태 유지

    render(<GuestLoginForm />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/guest");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/guest/login");
    expect(JSON.parse(init.body)).toEqual({ invite: "guest_1234.secretvalue" });
    expect(screen.getByText("입장 링크를 확인하는 중입니다...")).toBeTruthy();
  });

  it("링크가 거절되면 서버 안내와 아이디·비밀번호 폼을 보여 준다", async () => {
    window.history.replaceState(null, "", "/guest#guest_1234.bad");
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ error: "입장 링크가 올바르지 않거나 더 이상 사용할 수 없습니다." }),
    });

    const { container } = render(<GuestLoginForm />);

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "입장 링크가 올바르지 않거나 더 이상 사용할 수 없습니다."
    );
    expect(container.querySelector("form")?.hidden).toBe(false);
  });

  it("hash가 없으면 자동으로 요청하지 않는다", () => {
    window.history.replaceState(null, "", "/guest");
    render(<GuestLoginForm />);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
