import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import QaLogsTab from "@/components/admin/QaLogsTab";

// 콘솔 Q&A Logs — 한 턴의 사용자 입력과 응답을 한 카드에 나란히 보여 준다(2026-11-18).
const longAnswer = Array.from({ length: 20 }, (_, i) => `응답 줄 ${i + 1}`).join("\n");

const response = {
  total: 2,
  page: 1,
  pageSize: 30,
  logs: [
    {
      id: "q1",
      userId: 7,
      userEmail: "a@example.com",
      sessionId: "abcdef123456",
      turnIndex: 1,
      question: "RSI 30 이하에서 사줘",
      answer: "몇 종목까지 보유할까요?",
      answerKind: "clarification",
      chipAnswer: false,
      latencyMs: 2300,
      createdAt: "2026-11-18T01:00:00Z",
      strategy: null,
      strategySource: null,
    },
    {
      id: "q2",
      userId: null,
      userEmail: null,
      sessionId: "zzzz99998888",
      turnIndex: 3,
      question: "10종목",
      answer: longAnswer,
      answerKind: "coach",
      chipAnswer: true,
      latencyMs: 800,
      createdAt: "2026-11-18T01:01:00Z",
      strategy: null,
      strategySource: null,
    },
  ],
};

describe("QaLogsTab", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => response })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("턴마다 사용자 입력과 응답을 한 카드에 함께 보여 준다", async () => {
    render(<QaLogsTab />);

    const cards = await screen.findAllByTestId("qa-turn-card");
    expect(cards).toHaveLength(2);
    const first = within(cards[0]);
    expect(first.getByText("사용자 입력")).toBeInTheDocument();
    expect(first.getByText("널스탁 응답")).toBeInTheDocument();
    expect(first.getByText("RSI 30 이하에서 사줘")).toBeInTheDocument();
    expect(first.getByText("몇 종목까지 보유할까요?")).toBeInTheDocument();
    expect(first.getByText("a@example.com")).toBeInTheDocument();
    expect(within(cards[1]).getByText("비로그인")).toBeInTheDocument();
    expect(within(cards[1]).getByText("칩 선택")).toBeInTheDocument();
  });

  it("긴 응답은 접어 두고 버튼으로 펼친다", async () => {
    render(<QaLogsTab />);
    const cards = await screen.findAllByTestId("qa-turn-card");

    expect(within(cards[0]).queryByText("응답 전체 보기")).toBeNull();
    const toggle = within(cards[1]).getByText("응답 전체 보기");
    fireEvent.click(toggle);
    expect(within(cards[1]).getByText("접기")).toBeInTheDocument();
  });

  it("대화 전체보기는 그 대화로 필터한다", async () => {
    render(<QaLogsTab />);
    const cards = await screen.findAllByTestId("qa-turn-card");

    fireEvent.click(within(cards[0]).getByText("대화 전체보기"));

    await waitFor(() =>
      expect(vi.mocked(global.fetch).mock.calls.at(-1)?.[0]).toContain("sessionId=abcdef123456"),
    );
    expect(await screen.findByText("대화 필터 해제")).toBeInTheDocument();
  });
});
