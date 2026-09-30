import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import UserConversationPanel from "@/components/admin/UserConversationPanel";

// 콘솔 Users 탭 — 사용자를 고르면 그 사용자가 입력한 전략과 우리가 이해한 전략 카드를 본다(2026-09-30).
const response = {
  total: 1,
  page: 1,
  pageSize: 30,
  logs: [
    {
      id: "q1",
      sessionId: "abcdef123456",
      turnIndex: 2,
      question: "KOSPI200에서 RSI 30 이하 매수",
      answer: "[전략 요약 카드]",
      answerKind: "strategy",
      chipAnswer: false,
      createdAt: "2026-09-30T01:00:00Z",
      strategy: {
        summaryItems: [
          { label: "종목군", value: "KOSPI200" },
          { label: "매수", value: "RSI 30 이하", values: ["RSI 30 이하", "거래대금 100억 이상"] },
        ],
        parsed: { universe: ["KOSPI200"] },
      },
      strategySource: "chat_snapshot",
    },
  ],
};

describe("UserConversationPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => response })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("사용자의 입력과 우리가 이해한 전략 카드 항목을 보여 준다", async () => {
    render(<UserConversationPanel userId={31} email="g@guest.nullstock.im" />);

    expect(await screen.findByText("KOSPI200에서 RSI 30 이하 매수")).toBeInTheDocument();
    expect(screen.getByText("우리가 이해한 전략")).toBeInTheDocument();
    expect(screen.getByText("거래대금 100억 이상")).toBeInTheDocument();
    expect(screen.getByText("(사용자 대화 기록에서 복원)")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toContain("userId=31");
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toContain("strategyOnly=1");
  });

  it("토글로 모든 대화를 본다", async () => {
    render(<UserConversationPanel userId={31} email="g@guest.nullstock.im" />);
    await screen.findByText("KOSPI200에서 RSI 30 이하 매수");

    fireEvent.click(screen.getByText("모든 대화 보기"));

    await waitFor(() =>
      expect(vi.mocked(global.fetch).mock.calls.at(-1)?.[0]).not.toContain("strategyOnly"),
    );
  });
});
