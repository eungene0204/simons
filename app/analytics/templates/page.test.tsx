import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import StrategyTemplatesPage from "./page";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe("StrategyTemplatesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    push.mockClear();
    sessionStorage.clear();
  });

  it("전략 종류별 탭을 보여주고 선택한 종류의 템플릿만 보여준다", async () => {
    const user = userEvent.setup();

    render(<StrategyTemplatesPage />);

    expect(screen.getByRole("button", { name: "전체 전략 템플릿 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "가치투자 전략 템플릿 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "기술분석 전략 템플릿 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "모멘텀 전략 템플릿 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "복합전략 전략 템플릿 보기" })).toBeInTheDocument();
    expect(screen.queryByText("49개")).not.toBeInTheDocument();
    expect(screen.queryByText(/개의 전략 템플릿/)).not.toBeInTheDocument();

    expect(screen.getByText("저PBR 대형주 장기보유")).toBeInTheDocument();
    expect(screen.getByText("이평선 골든크로스 따라가기")).toBeInTheDocument();

    const firstTemplateCard = screen.getByRole("button", { name: /저PBR 대형주 장기보유/i });
    const categoryBadge = within(firstTemplateCard).getByText("가치투자");
    expect(categoryBadge.className).toContain("bg-black");
    expect(categoryBadge.className).toContain("text-emerald-300");
    expect(categoryBadge.className).not.toContain("border");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "기술분석 전략 템플릿 보기" }));
    });

    expect(screen.getByText("이평선 골든크로스 따라가기")).toBeInTheDocument();
    expect(screen.queryByText("저PBR 대형주 장기보유")).not.toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "모멘텀 전략 템플릿 보기" }));
    });

    expect(screen.getByText("신고가 돌파주 짧게 보유")).toBeInTheDocument();
    expect(screen.queryByText("이평선 골든크로스 따라가기")).not.toBeInTheDocument();
  });

  it("템플릿을 누르면 편집 가능한 모달을 보여주고 전략 생성 시 전략 채팅으로 이동한다", async () => {
    const user = userEvent.setup();
    const editedPrompt = "편집한 전략 내용으로 바로 전략 생성";

    render(<StrategyTemplatesPage />);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));
    });

    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
    expect(push).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog", { name: "이평선 골든크로스 따라가기" });
    const promptInput = within(dialog).getByLabelText("전략 내용");
    expect((promptInput as HTMLTextAreaElement).value).toContain("골든크로스");

    await act(async () => {
      fireEvent.change(promptInput, { target: { value: editedPrompt } });
    });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "전략 생성" }));
    });

    expect(screen.queryByRole("button", { name: "템플릿 사용" })).not.toBeInTheDocument();
    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(editedPrompt);
    expect(push).toHaveBeenCalledWith("/analytics/chat");
  });

  it("미리보기 모달에서 취소를 누르면 전략 채팅으로 이동하지 않는다", async () => {
    const user = userEvent.setup();

    render(<StrategyTemplatesPage />);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));
    });
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "취소" }));
    });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });
});
