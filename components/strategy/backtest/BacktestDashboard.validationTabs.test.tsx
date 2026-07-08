// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: () =>
      ({ children, layoutId: _layoutId, ...props }: any) => <div {...props}>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({
  default: () => null,
  WalkForwardPanel: ({ optimizationTargets = [] }: any) => (
    <div>
      <button type="button">워크포워드 분석 시작</button>
      {optimizationTargets.map((target: any) => (
        <span key={target.id}>{target.label}</span>
      ))}
    </div>
  ),
}));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

import BacktestDashboard from "./BacktestDashboard";

function buildDates(length: number) {
  return Array.from({ length }, (_, index) => {
    const date = new Date(Date.UTC(2024, 0, 1 + index));
    return date.toISOString().slice(0, 10);
  });
}

function buildEquity(length: number) {
  let value = 10_000_000;
  return Array.from({ length }, (_, index) => {
    value *= index % 9 === 0 ? 0.992 : 1.006;
    return Math.round(value);
  });
}

const equity = buildEquity(120);
const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  symbols: ["005930"],
  totalReturn: 12.4,
  cagr: 8.2,
  buyAndHoldReturn: 6.1,
  maxDrawdown: -9.8,
  winRate: 54.3,
  profitFactor: 1.44,
  sharpe: 1.12,
  sortino: 1.38,
  trades: 18,
  finalEquity: equity[equity.length - 1],
  initialCapital: 10_000_000,
  equity,
  dates: buildDates(equity.length),
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

async function renderDashboard(planId: "FREE" | "PREMIUM", props: Record<string, any> = {}) {
  const fetchMock = vi.fn((url: string) => {
    if (url === "/api/user/plan") {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            plan: {
              planId,
              name: planId,
            },
          }),
      });
    }

    if (url === "/api/stocks/names") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }

    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });

  vi.stubGlobal("fetch", fetchMock);

  let view: ReturnType<typeof render> | undefined;
  await act(async () => {
    view = render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave
        aiSummary="과거 데이터 기준 요약"
        aiScore={61}
        {...props}
      />
    );
  });
  return view;
}

describe("BacktestDashboard 전략 최적화 페이지", () => {
  beforeEach(() => {
    cleanup();
  });

  it("FREE 플랜에서는 전략 최적화 진입 시 프리미엄 잠금 안내와 플랜 변경 버튼을 표시한다", async () => {
    await renderDashboard("FREE");
    const user = userEvent.setup();

    expect(screen.getByTestId("backtest-tab-content")).not.toHaveClass("flex-1");
    expect(screen.getByTestId("backtest-dashboard-footer")).toHaveClass("px-0", "py-3", "mt-auto");

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    // 게이트 화면에서는 워크포워드/몬테카를로 모델 선택이 노출되지 않는다.
    expect(screen.getByText("전략 최적화는 프리미엄 플랜 전용 기능입니다")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "몬테카를로" })).not.toBeInTheDocument();
    expect(screen.queryByText("몬테카를로 시뮬레이션")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "플랜 변경" })).toHaveAttribute("href", "/pricing");
  });

  it("PREMIUM 플랜에서는 전략 최적화 페이지에서 워크포워드 CTA와 몬테카를로 결과를 노출한다", async () => {
    await renderDashboard("PREMIUM", {
      onWalkForward: vi.fn(),
      strategySummary: {
        strategyName: "저PBR 장기보유",
        universeName: "KOSPI 200",
        blockNames: ["PBR <= 1"],
        entryBlocks: ["PBR <= 1"],
        exitBlocks: ["손절 -12% 하락시 매도", "익절 30% 이상 수익시 매도", "최대 126일 보유 후 매도"],
        positionText: "최대 8종목 · 126일 보유",
        riskText: "손절 12%, 익절 30%",
      },
    });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    // 기본 선택은 워크포워드
    expect(screen.getByRole("button", { name: "워크포워드" })).toHaveClass("border-sky-400/40");
    expect(screen.getByRole("button", { name: "워크포워드" })).toHaveClass("bg-transparent");
    expect(screen.getByRole("button", { name: "워크포워드" })).not.toHaveClass("bg-sky-500/10");
    expect(await screen.findByRole("button", { name: "워크포워드 분석 시작" })).toBeInTheDocument();
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("py-4");
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("flex-1");
    expect(screen.getByText("PBR")).toBeInTheDocument();
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByText("익절라인")).toBeInTheDocument();
    expect(screen.getByText("보유기간")).toBeInTheDocument();
    expect(screen.getByText("보유종목수")).toBeInTheDocument();
    expect(screen.queryByText("PBR <= 1")).not.toBeInTheDocument();
    expect(screen.queryByText("손절 -12% 하락시 매도")).not.toBeInTheDocument();
    expect(screen.queryByText("익절 30% 이상 수익시 매도")).not.toBeInTheDocument();
    expect(screen.queryByText("최대 126일 보유 후 매도")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "몬테카를로" }));
    expect(screen.queryByText("Premium Validation")).not.toBeInTheDocument();
    expect(screen.queryByText("결과는 과거 데이터 기반 시뮬레이션이며 미래 성과를 보장하지 않습니다.")).not.toBeInTheDocument();
    expect(screen.getByText(/백테스트 결과를 여러 방식으로 다시 섞어 보며/)).toBeInTheDocument();
    expect(screen.queryByText(/백테스트 equity curve의 일별 수익률/)).not.toBeInTheDocument();
    expect(screen.queryByText(/블록 방식은 여러 날을 이어 뽑아/)).not.toBeInTheDocument();
    expect(screen.getByText("21거래일 단위로 수익률 흐름을 다시 조합해, 며칠간 이어지는 상승과 하락 패턴도 함께 살펴봅니다.")).toBeInTheDocument();
    expect(screen.queryByText(/21거래일씩 묶어 섞어/)).not.toBeInTheDocument();
    expect(screen.queryByText(/21거래일 블록으로 이어 뽑아 자기상관을 보존합니다/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "몬테카를로 실행" }));

    await waitFor(() => {
      expect(screen.getByText("양수 CAGR 확률")).toBeInTheDocument();
      expect(screen.getByText("x축: CAGR 구간")).toBeInTheDocument();
      expect(screen.getByText("x축: MDD 구간")).toBeInTheDocument();
      expect(screen.getAllByText("y축: 시나리오 수")).toHaveLength(2);
      // 결과 하단에 일상 언어 "쉽게 이해하기" 섹션이 표시된다
      const plainSummary = screen.getByTestId("result-plain-summary");
      expect(plainSummary).toBeInTheDocument();
      expect(plainSummary).toHaveClass("border-white/[0.08]");
      expect(plainSummary).not.toHaveClass("bg-sky-500/[0.05]");
      expect(screen.getByText("쉽게 이해하기")).toHaveClass("text-gray-500");
      expect(screen.getByText(/일별 수익률을 무작위로 다시 섞어/)).toBeInTheDocument();
      expect(screen.getByText(/30% 넘게 하락한 시나리오는/)).toBeInTheDocument();
      expect(screen.queryByText("위 내용은 모두 과거 데이터 기반 시뮬레이션 결과이며, 미래 수익은 보장되지 않습니다.")).not.toBeInTheDocument();
    });
  });

  it("일반 탭을 클릭하면 전략 최적화 페이지를 닫는다", async () => {
    await renderDashboard("PREMIUM");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "종목 분석" }));
    expect(screen.queryByTestId("backtest-optimization-page")).not.toBeInTheDocument();
    expect(screen.getByTestId("backtest-tab-content")).toBeInTheDocument();
  });

  it("'결과 닫기'는 최적화 실행 결과가 나온 뒤에만 노출되고, 누르면 페이지가 닫힌다", async () => {
    await renderDashboard("PREMIUM");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    const optimizationPage = await screen.findByTestId("backtest-optimization-page");

    // 실행 전 설정 화면에는 '결과 닫기' 버튼이 없어야 한다.
    await user.click(screen.getByRole("button", { name: "몬테카를로" }));
    expect(within(optimizationPage).queryByRole("button", { name: "결과 닫기" })).not.toBeInTheDocument();

    // 실행해 결과가 나온 뒤에만 '결과 닫기'가 노출된다.
    await user.click(await screen.findByRole("button", { name: "몬테카를로 실행" }));
    await waitFor(() => {
      expect(screen.getByText("양수 CAGR 확률")).toBeInTheDocument();
    });
    const closeButton = within(optimizationPage).getByRole("button", { name: "결과 닫기" });

    // 누르기 전까지는 최적화 페이지가 유지되고, 누르면 결과 탭으로 돌아간다.
    expect(screen.getByTestId("backtest-optimization-page")).toBeInTheDocument();
    await user.click(closeButton);
    expect(screen.queryByTestId("backtest-optimization-page")).not.toBeInTheDocument();
    expect(screen.getByTestId("backtest-tab-content")).toBeInTheDocument();
  });
});
