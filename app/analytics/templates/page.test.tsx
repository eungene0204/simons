import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyTemplatesPage from "./page";
import { EXAMPLES, shuffleExamples } from "@/components/strategy/StrategyExampleTabs";

const beginStrategyChatNavigation = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("../new/chatNavigation", () => ({
  beginStrategyChatNavigation: (
    prompt: string,
    navigate: (url: string) => void
  ) => {
    beginStrategyChatNavigation(prompt);
    navigate("/analytics/chat");
  },
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

// 목록은 마운트 후 무작위로 섞인다. Fisher-Yates에서 Math.random()이 1에 수렴하면
// 항상 j === i(자기 자신과 교환)이라 원래 순서가 유지된다 — 순서에 의존하는 아래
// 검증들은 이 고정으로 예시 목록 정의 순서를 그대로 본다.
function freezeExampleOrder() {
  vi.spyOn(Math, "random").mockReturnValue(0.999999);
}

describe("StrategyTemplatesPage", () => {
  beforeEach(() => {
    freezeExampleOrder();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    beginStrategyChatNavigation.mockClear();
    push.mockClear();
    sessionStorage.clear();
  });

  it("전략 종류별 탭을 보여주고 선택한 종류의 템플릿만 보여준다", async () => {
    render(<StrategyTemplatesPage />);

    expect(screen.getByRole("heading", { name: "백테스트 입력 예시" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "전략연구소로 돌아가기" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "전체 백테스트 예시 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "가치투자 백테스트 예시 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "기술분석 백테스트 예시 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "모멘텀 백테스트 예시 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "복합전략 백테스트 예시 보기" })).toBeInTheDocument();
    const exampleNotice = screen.getByRole("contentinfo", { name: "백테스트 입력 예시 안내" });
    expect(within(exampleNotice).getByText(
      "백테스트 입력 예시에 쓰인 수치는 단순 예시값이며, 투자 추천이나 미래 성과를 의미하지 않습니다."
    )).toBeInTheDocument();
    expect(screen.queryByText("49개")).not.toBeInTheDocument();
    expect(screen.queryByText(/개의 전략 템플릿/)).not.toBeInTheDocument();

    expect(screen.getByText("저PBR 대형주 장기보유")).toBeInTheDocument();
    expect(screen.getByText("이평선 골든크로스 따라가기")).toBeInTheDocument();

    const firstTemplateCard = screen.getByRole("button", { name: /저PBR 대형주 장기보유/i });
    const categoryBadge = within(firstTemplateCard).getByText("가치투자");
    expect(categoryBadge.className).toContain("bg-black");
    expect(categoryBadge.className).toContain("text-emerald-300");
    expect(categoryBadge.className).not.toContain("border");

    fireEvent.click(screen.getByRole("button", { name: "기술분석 백테스트 예시 보기" }));

    expect(screen.getByText("이평선 골든크로스 따라가기")).toBeInTheDocument();
    expect(screen.queryByText("저PBR 대형주 장기보유")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "모멘텀 백테스트 예시 보기" }));

    expect(screen.getByText("신고가 돌파주 짧게 보유")).toBeInTheDocument();
    expect(screen.queryByText("이평선 골든크로스 따라가기")).not.toBeInTheDocument();
  });

  it("마운트 후 예시 순서를 섞어서 보여준다", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const shuffled = shuffleExamples(EXAMPLES);
    const visible = shuffled.slice(0, 24);
    const dropped = EXAMPLES.slice(0, 24).find((example) => !visible.includes(example));

    render(<StrategyTemplatesPage />);

    expect(shuffled[0].title).not.toBe(EXAMPLES[0].title);
    expect(screen.getByText(visible[0].title)).toBeInTheDocument();
    expect(dropped).toBeDefined();
    expect(screen.queryByText(dropped!.title)).not.toBeInTheDocument();
  });

  it("ETF·테마 탭은 해당 종류의 예시만 보여준다", () => {
    render(<StrategyTemplatesPage />);

    fireEvent.click(screen.getByRole("button", { name: "ETF 백테스트 예시 보기" }));

    expect(screen.getByText("ETF 골든크로스 따라가기")).toBeInTheDocument();
    expect(screen.queryByText("저PBR 대형주 장기보유")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "테마 백테스트 예시 보기" }));

    expect(screen.getByText("반도체 업종 골든크로스")).toBeInTheDocument();
    expect(screen.queryByText("ETF 골든크로스 따라가기")).not.toBeInTheDocument();
  });

  it("전체 목록은 처음에 일부만 렌더링하고 더 보기로 나머지를 노출한다", () => {
    render(<StrategyTemplatesPage />);

    expect(screen.getByText("볼린저 중심선 재돌파 스윙")).toBeInTheDocument();
    expect(screen.queryByText("상대강도 상위주 월간 교체")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));

    expect(screen.getByText("상대강도 상위주 월간 교체")).toBeInTheDocument();
  });

  it("예시를 누르면 편집 가능한 모달을 보여주고 시작 시 전략 채팅으로 이동한다", async () => {
    const editedPrompt = "편집한 백테스트 예시로 시작";

    render(<StrategyTemplatesPage />);

    fireEvent.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));

    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
    expect(beginStrategyChatNavigation).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog", { name: "이평선 골든크로스 따라가기" });
    const backdrop = screen.getByTestId("strategy-template-preview-backdrop");
    expect(backdrop.className).toContain("backdrop-blur-[12px]");
    expect(backdrop.className).toContain("[backdrop-filter:blur(12px)]");
    expect(backdrop.className).toContain("[-webkit-backdrop-filter:blur(12px)]");
    expect(screen.getByTestId("strategy-templates-page-background").className).toContain("blur-[6px]");
    expect(within(dialog).queryByText(/백테스트 입력 예시에 쓰인 수치는 단순 예시값/)).not.toBeInTheDocument();
    const promptInput = within(dialog).getByLabelText("백테스트 예시 내용");
    expect((promptInput as HTMLTextAreaElement).value).toContain("골든크로스");

    fireEvent.change(promptInput, { target: { value: editedPrompt } });
    fireEvent.click(screen.getByRole("button", { name: "예시로 시작" }));

    expect(screen.queryByRole("button", { name: "템플릿 사용" })).not.toBeInTheDocument();
    expect(beginStrategyChatNavigation).toHaveBeenCalledWith(editedPrompt);
    expect(push).toHaveBeenCalledWith("/analytics/chat");
  });

  it("미리보기 모달에서 취소를 누르면 전략 채팅으로 이동하지 않는다", async () => {
    render(<StrategyTemplatesPage />);

    fireEvent.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));
    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
    expect(beginStrategyChatNavigation).not.toHaveBeenCalled();
  });
});
