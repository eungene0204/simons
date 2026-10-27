import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SimulationCardGrid, type SimulationCard } from "./SimulationCardGrid";

const ready: SimulationCard = {
  publicId: "pub1", name: "RSI 전략", description: "설명", status: "ready",
  window: { actualStart: "2023-10-27", actualEnd: "2026-10-23", dataAsOf: "2026-10-23" },
  summary: { totalReturnPct: 12.345, totalProfit: 1234567, maxDrawdownPct: -8.5 },
  curve: { dates: ["a", "b", "c"], returnPct: [0, 5, 12.3] },
};
const respond = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(cleanup);

describe("SimulationCardGrid", () => {
  it("저장된 결과를 카드로 보이고 클릭하면 publicId를 넘긴다", async () => {
    fetchMock.mockResolvedValue(respond({ items: [ready], hasNext: false }));
    const onOpen = vi.fn();
    render(<SimulationCardGrid onOpen={onOpen} />);
    expect(await screen.findByText("RSI 전략")).toBeTruthy();
    expect(screen.getByText("+12.35%")).toBeTruthy();
    expect(screen.getByText("₩1,234,567")).toBeTruthy();
    expect(screen.getByText("-8.50%")).toBeTruthy();
    expect(screen.getByRole("img", { name: "누적 수익률 추이" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /RSI 전략/ }));
    expect(onOpen).toHaveBeenCalledWith("pub1");
  });

  it("결과가 없는 상태는 0%나 빈 그래프가 아니라 상태 문구를 보인다", async () => {
    fetchMock.mockResolvedValue(respond({
      items: [
        { publicId: "p", name: "대기", status: "pending", description: null },
        { publicId: "u", name: "불가", status: "unavailable", reason: "UNSUPPORTED_REGION", description: null },
        { publicId: "f", name: "실패", status: "failed", reason: "ENGINE_ERROR", description: null },
      ],
      hasNext: false,
    }));
    render(<SimulationCardGrid />);
    expect(await screen.findByText("원본 결과를 계산하고 있습니다.")).toBeTruthy();
    expect(screen.getByText("미국 시장 전략은 지원하지 않습니다.")).toBeTruthy();
    expect(screen.getByText("계산에 실패해 잠시 후 다시 시도합니다.")).toBeTruthy();
    expect(screen.queryByText("ENGINE_ERROR")).toBeNull();     // 내부 코드는 화면에 나가지 않는다
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText(/0\.00%/)).toBeNull();
  });

  it("갱신 중 항목은 저장된 값과 함께 배지를 보인다", async () => {
    fetchMock.mockResolvedValue(respond({ items: [{ ...ready, status: "refreshing" }], hasNext: false }));
    render(<SimulationCardGrid />);
    expect(await screen.findByText("갱신 중")).toBeTruthy();
    expect(screen.getByText("+12.35%")).toBeTruthy();
  });

  it("검색은 q를 붙여 첫 페이지부터 다시 부르고, 더 보기는 다음 페이지를 이어 붙인다", async () => {
    fetchMock
      .mockResolvedValueOnce(respond({ items: [ready], hasNext: true }))
      .mockResolvedValueOnce(respond({ items: [{ ...ready, publicId: "pub2", name: "두번째" }], hasNext: false }))
      .mockResolvedValueOnce(respond({ items: [], hasNext: false }));
    render(<SimulationCardGrid />);
    await screen.findByText("RSI 전략");
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    await screen.findByText("두번째");
    expect(screen.getByText("RSI 전략")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toContain("page=2");

    fireEvent.change(screen.getByLabelText("전략 이름 검색"), { target: { value: " 없는이름 " } });
    fireEvent.click(screen.getByRole("button", { name: "검색" }));
    await screen.findByText("검색 결과가 없습니다.");
    expect(fetchMock.mock.calls[2][0]).toContain("q=%EC%97%86%EB%8A%94%EC%9D%B4%EB%A6%84");
    expect(fetchMock.mock.calls[2][0]).toContain("page=1");
  });

  it("목록 요청이 실패하면 오류와 다시 시도를 보이고 빈 목록 문구는 내지 않는다", async () => {
    fetchMock.mockResolvedValueOnce(respond({ code: "LIST_FAILED" }, false)).mockResolvedValueOnce(respond({ items: [ready], hasNext: false }));
    render(<SimulationCardGrid />);
    await screen.findByRole("alert");
    expect(screen.queryByText("공개된 전략이 아직 없습니다.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.getByText("RSI 전략")).toBeTruthy());
  });
});
