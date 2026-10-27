import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import StrategySimulationPage from "./page";

const { regionMock, notFoundMock } = vi.hoisted(() => ({
  regionMock: { current: "kr" },
  notFoundMock: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("@/lib/geo/server", () => ({ getRequestRegion: () => regionMock.current }));
vi.mock("next/navigation", () => ({ notFound: notFoundMock }));
vi.mock("@/components/strategy-simulation/SimulationBrowser", () => ({ SimulationBrowser: () => <div data-testid="browser" /> }));

beforeEach(() => {
  regionMock.current = "kr";
  notFoundMock.mockClear();
});

describe("전략 시뮬레이션 페이지", () => {
  it("한국 지역에서는 목록을 렌더하고 공통 안내를 한 번 보인다", () => {
    const html = renderToStaticMarkup(<StrategySimulationPage />);
    expect(html).toContain('data-testid="browser"');
    expect(html.split("미래 수익을 보장하지 않습니다").length - 1).toBe(1);
    expect(html).toMatch(/<footer[^>]*>[\s\S]*미래 수익을 보장하지 않습니다[\s\S]*<\/footer>/);
    expect(notFoundMock).not.toHaveBeenCalled();
  });

  it("미국 지역(/us) 주소로 직접 들어오면 404로 처리한다", () => {
    regionMock.current = "us";
    expect(() => renderToStaticMarkup(<StrategySimulationPage />)).toThrow("NEXT_NOT_FOUND");
    expect(notFoundMock).toHaveBeenCalled();
  });
});
