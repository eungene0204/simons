import { describe, expect, it, vi } from "vitest";

vi.mock("./BacktestHistoryView", () => ({
  default: () => null,
}));

const BacktestHistoryPage = (await import("./page")).default;
const pageModule = await import("./page");

describe("/backtest 페이지", () => {
  it("목록 조회 없이 뷰만 렌더한다(서버 왕복을 기다리지 않는다)", () => {
    const element = BacktestHistoryPage();

    expect(element.props).toEqual({});
    // force-dynamic 서버 렌더로 되돌리면 탭 진입마다 서버 조회를 기다려 매번 로딩이 보인다.
    expect((pageModule as Record<string, unknown>).dynamic).toBeUndefined();
  });
});
