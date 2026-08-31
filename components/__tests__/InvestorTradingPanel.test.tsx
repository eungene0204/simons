import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import InvestorTradingPanel from "@/components/order/InvestorTradingPanel";

describe("InvestorTradingPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("미국 티커는 API 를 호출하지 않고 미지원 안내를 표시한다", () => {
    render(<InvestorTradingPanel symbol="INTC" />);

    expect(screen.getByText("미국 종목에선 지원하지 않습니다")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("한국 종목은 기존대로 매매동향을 조회해 표시한다", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        data: [
          {
            date: "2026-08-28",
            individual_net: 1000,
            foreign_net: -500,
            institutional_net: -500,
          },
        ],
      }),
    } as never);

    render(<InvestorTradingPanel symbol="005930" />);

    await waitFor(() => {
      expect(screen.getByText("+1,000")).toBeInTheDocument();
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/stock/005930/investor-trading",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(screen.queryByText("미국 종목에선 지원하지 않습니다")).not.toBeInTheDocument();
  });
});
