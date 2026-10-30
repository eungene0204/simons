import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { addSeries, setData, fitContent, createChart } = vi.hoisted(() => {
  const setData = vi.fn();
  const fitContent = vi.fn();
  const addSeries = vi.fn((_type: unknown, _options?: unknown) => ({ setData }));
  const createChart = vi.fn(() => ({
    addSeries,
    timeScale: () => ({ fitContent }),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }));
  return { addSeries, setData, fitContent, createChart };
});

vi.mock("lightweight-charts", () => ({
  createChart,
  BaselineSeries: "BaselineSeries",
  ColorType: { Solid: "solid" },
  LineType: { Simple: "Simple" },
}));

import AccountReturnChart, { formatAxisDate, formatCrosshairDate } from "./AccountReturnChart";

const respond = (points: { time: string; returnPct: number }[], range = "all") =>
  vi.fn(async () => new Response(JSON.stringify({ range, points }), { status: 200 }));

describe("날짜 표기", () => {
  it("축 눈금과 십자선 라벨에 월을 함께 표시한다 — 날짜만 보이면 몇 월인지 알 수 없다", () => {
    const businessDay = { year: 2026, month: 10, day: 21 };

    expect(formatAxisDate(businessDay, "ko-KR")).toBe("10월 21일");
    expect(formatAxisDate("2026-10-21", "en-US")).toBe("Oct 21");
    expect(formatCrosshairDate(businessDay, "ko-KR")).toBe("2026년 10월 21일");
  });
});

describe("AccountReturnChart", () => {
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(600);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(260);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("기본 전체 기간으로 조회하고 일별 수익률 점을 0% 기준선 위에 그린다", async () => {
    const fetchMock = respond([
      { time: "2026-10-28", returnPct: 1.5 },
      { time: "2026-10-29", returnPct: -0.5 },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountReturnChart accountId="acc-1" />);

    await waitFor(() => expect(setData).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("/api/virtual-account/acc-1/snapshots?range=all", { cache: "no-store" });
    expect(addSeries.mock.calls[0][1]).toMatchObject({ baseValue: { type: "price", price: 0 } });
    const options = (createChart.mock.calls[0] as unknown[])[1] as {
      timeScale: { tickMarkFormatter: (time: unknown) => string };
      localization: { timeFormatter: (time: unknown) => string };
    };
    expect(options.timeScale.tickMarkFormatter({ year: 2026, month: 10, day: 28 })).toBe("10월 28일");
    expect(options.localization.timeFormatter({ year: 2026, month: 10, day: 28 })).toBe("2026년 10월 28일");
    expect(setData).toHaveBeenCalledWith([
      { time: "2026-10-28", value: 1.5 },
      { time: "2026-10-29", value: -0.5 },
    ]);
  });

  it("기간 버튼을 누르면 그 기간으로 다시 조회한다", async () => {
    const fetchMock = respond([{ time: "2026-10-28", returnPct: 0 }, { time: "2026-10-29", returnPct: 1 }]);
    vi.stubGlobal("fetch", fetchMock);
    render(<AccountReturnChart accountId="acc-1" />);
    await waitFor(() => expect(setData).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "1개월" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith("/api/virtual-account/acc-1/snapshots?range=1m", { cache: "no-store" })
    );
    expect(screen.getByRole("button", { name: "1개월" })).toHaveAttribute("aria-pressed", "true");
  });

  it("점이 하나뿐이면(오늘 개설) 차트 대신 안내를 보인다", async () => {
    vi.stubGlobal("fetch", respond([{ time: "2026-10-30", returnPct: 0 }]));

    render(<AccountReturnChart accountId="acc-1" />);

    expect(await screen.findByText(/아직 표시할 일별 기록이 없습니다/)).toBeInTheDocument();
    expect(createChart).not.toHaveBeenCalled();
  });

  it("조회에 실패하면 오류 안내를 보인다", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));

    render(<AccountReturnChart accountId="acc-1" />);

    expect(await screen.findByText("수익률 변화를 불러오지 못했습니다.")).toBeInTheDocument();
    expect(fitContent).not.toHaveBeenCalled();
  });
});
