import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import OrderBook from "@/components/order/OrderBook";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("OrderBook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("실호가 조회 실패 시 에러 메시지를 보여주지 않는다", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "error" }),
    });

    render(<OrderBook symbol="005930" />);

    await waitFor(() => {
      expect(screen.queryByText("실제 호가 데이터를 아직 받지 못했습니다")).not.toBeInTheDocument();
    });
  });
});
