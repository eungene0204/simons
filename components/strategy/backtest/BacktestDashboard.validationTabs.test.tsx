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
  WalkForwardPanel: ({ optimizationTargets = [], onDesignChange, resultContainer }: any) => {
    const React = require("react");
    const { createPortal } = require("react-dom");
    const [done, setDone] = React.useState(false);
    const design = (result: any) => ({
      totalBars: 240, trainBars: 120, validationBars: 60, anchor: false, windows: 2,
      methodLabel: "베이지안 30회", targetMetricLabel: "CAGR", parameters: [], edit: null, blockedAt: null, running: false,
      plan: { totalBacktests: 62, estimateLabel: "약 1분", blockedReason: null, suggestions: [], note: null },
      result,
    });
    React.useEffect(() => {
      onDesignChange?.(design(done ? { wfe: 0.8, wfeTierText: null, avgOosCagr: 5, windows: [] } : null));
    }, [done]);
    return (
      <div>
        <button type="button">워크포워드 분석 시작</button>
        <button type="button" onClick={() => setDone(true)}>(테스트) 결과 만들기</button>
        <button type="button" onClick={() => setDone(false)}>(테스트) 재설정</button>
        {optimizationTargets.map((target: any) => (
          <span key={target.id}>{target.label}</span>
        ))}
        {done && resultContainer && createPortal(<p>워크포워드 결과 본문</p>, resultContainer)}
      </div>
    );
  },
}));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

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

  it("모바일에서는 결과 툴바를 쌓고 lg에서 기존 가로 배치를 복원한다", async () => {
    await renderDashboard("PREMIUM", {
      promptText: "KOSPI 저PBR 전략을 과거 데이터로 검증",
    });
    const user = userEvent.setup();

    expect(screen.getByTestId("backtest-result-toolbar")).toHaveClass(
      "flex-col",
      "items-stretch",
      "lg:flex-row",
      "lg:items-center",
      "lg:justify-between"
    );
    expect(screen.getByTestId("backtest-result-actions")).toHaveClass(
      "w-full",
      "flex-wrap",
      "lg:w-auto",
      "lg:flex-nowrap"
    );

    await user.click(screen.getByRole("button", { name: "내 전략" }));
    expect(screen.getByTestId("backtest-prompt-popover")).toHaveClass(
      "left-4",
      "right-4",
      // 버튼이 전략 기간 옆(좌측)으로 옮겨져 lg에서는 왼쪽 정렬로 펼친다.
      "lg:right-auto",
      "lg:left-0",
      "lg:w-96"
    );
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
    expect(screen.getByTestId("backtest-optimization-page")).toHaveClass(
      "px-4",
      "py-8",
      "lg:px-6",
      "lg:py-10"
    );
    expect(screen.getByText(/프리미엄 플랜을 이용하시면/)).toHaveClass("lg:whitespace-nowrap");
    expect(screen.getByText(/프리미엄 플랜을 이용하시면/)).not.toHaveClass("whitespace-nowrap");
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
    // 검증 연구소 레이아웃 — 툴바(실험 탭) + 캔버스(검증 대상·방법 노트 참고 노드 + 실험 단계) + 조정 칸
    expect(screen.getByTestId("backtest-optimization-page")).toHaveClass("flex-col");
    expect(screen.getByTestId("validation-lab-toolbar")).toHaveTextContent("검증 연구소");
    expect(within(screen.getByTestId("validation-lab-toolbar")).getByRole("tab", { name: "워크포워드" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary")).toBeNull();

    // 기본 선택은 워크포워드 — 선택 상태는 강조색이 아니라 중립 면(UI 가이드라인 §2)
    expect(screen.getByRole("tab", { name: "워크포워드" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "워크포워드" }).parentElement).toHaveClass("bg-white/[0.12]");
    expect(screen.getByRole("tab", { name: "몬테카를로" })).toHaveAttribute("aria-selected", "false");
    expect(await screen.findByRole("button", { name: "워크포워드 분석 시작" })).toBeInTheDocument();
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("py-4");
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("flex-1");
    expect(screen.getByText("PBR")).toBeInTheDocument();
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByText("익절라인")).toBeInTheDocument();
    expect(screen.getByText("보유기간")).toBeInTheDocument();
    expect(screen.getByText("보유종목수")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "몬테카를로" }));
    expect(screen.queryByText("Premium Validation")).not.toBeInTheDocument();
    expect(screen.queryByText("결과는 과거 데이터 기반 시뮬레이션이며 미래 성과를 보장하지 않습니다.")).not.toBeInTheDocument();
    expect(screen.getByText(/백테스트 결과를 여러 방식으로 다시 섞어 보며/)).toBeInTheDocument();
    // 검증 대상 전략의 조건(PBR 등)을 몬테카를로 화면에 노출한다.
    expect(screen.getByTestId("optimization-strategy-summary")).toBeInTheDocument();
    expect(screen.getByText("PBR <= 1")).toBeInTheDocument();
    expect(screen.getByText("검증 대상 전략")).toBeInTheDocument();
    expect(screen.getByText("PBR <= 1")).not.toHaveClass("border");
    expect(screen.getByText("PBR <= 1")).not.toHaveClass("bg-sky-500/[0.08]");
    expect(screen.getByText("PBR <= 1")).toHaveClass("text-gray-200");
    expect(screen.getByText("손절 12%, 익절 30%")).not.toHaveClass("bg-white/[0.05]");
    expect(screen.getByText("손절 12%, 익절 30%")).toHaveClass("text-gray-200");
    expect(screen.queryByText(/백테스트 equity curve의 일별 수익률/)).not.toBeInTheDocument();
    expect(screen.queryByText(/블록 방식은 여러 날을 이어 뽑아/)).not.toBeInTheDocument();
    expect(screen.getByText("21거래일 단위로 수익률 흐름을 다시 조합해, 며칠간 이어지는 상승과 하락 패턴도 함께 살펴봅니다.")).toBeInTheDocument();
    expect(screen.queryByText(/21거래일씩 묶어 섞어/)).not.toBeInTheDocument();
    expect(screen.queryByText(/21거래일 블록으로 이어 뽑아 자기상관을 보존합니다/)).not.toBeInTheDocument();
    expect(screen.getByTestId("validation-lab-canvas")).toBeInTheDocument();
    // 검증 대상 전략은 왼쪽 레일이 아니라 캔버스의 참고 노드다.
    const canvas = screen.getByTestId("validation-lab-canvas");
    expect(within(canvas).getByTestId("experiment-node-strategy")).toContainElement(screen.getByTestId("optimization-strategy-summary"));
    expect(screen.queryByTestId("validation-lab-method-notes")).toBeNull();
    // 결과는 캔버스가 아니라 따로 보는 결과 화면에 나온다 — 실행 전에는 숨어 있다.
    expect(screen.getByTestId("monte-carlo-result-page")).toHaveClass("hidden");
    expect(screen.queryByTestId("monte-carlo-report-node")).toBeNull();
    // 실행 버튼은 조정 칸이 아니라 툴바 오른쪽 끝에 있다.
    expect(within(screen.getByTestId("validation-lab-run-slot")).getByRole("button", { name: "몬테카를로 실행" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "몬테카를로 실행" }));

    await waitFor(() => {
      expect(screen.getByText("양수 CAGR 확률")).toBeInTheDocument();
      expect(screen.queryByText("중앙 CAGR")).not.toBeInTheDocument();
      expect(screen.queryByText("하위 5% CAGR")).not.toBeInTheDocument();
      expect(screen.queryByText("상위 95% MDD")).not.toBeInTheDocument();
      expect(screen.getByTestId("monte-carlo-result-header")).toHaveClass(
        "flex-col",
        "items-stretch",
        "sm:flex-row",
        "sm:items-center"
      );
      expect(screen.getByTestId("monte-carlo-fan-figure")).toBeInTheDocument();
      expect(screen.getByText("x축: CAGR 구간")).toBeInTheDocument();
      expect(screen.getByText("x축: MDD 구간")).toBeInTheDocument();
      expect(screen.getAllByText("y축: 시나리오 수")).toHaveLength(2);
      // CAGR은 순서와 무관해 '분포 내 위치' 카드를 두지 않는다 — 중앙값 카드로 대체(08-19 감사)
      expect(screen.queryByText("실제 CAGR")).not.toBeInTheDocument();
      expect(screen.queryByText(/분포 상위/)).not.toBeInTheDocument();
      expect(screen.getByText("CAGR 중앙값").closest("div.rounded-xl")).toHaveClass(
        "border-white/[0.08]",
        "bg-white/[0.03]"
      );
      expect(screen.getByText("원래 순서 MDD").closest("div.rounded-xl")).toHaveClass(
        "border-white/[0.08]",
        "bg-white/[0.03]"
      );
      expect(screen.getByText("CAGR 중앙값")).toHaveClass("text-gray-500");
      expect(screen.getByText("원래 순서 MDD")).toHaveClass("text-gray-500");
      // 실행 설정(방식·반복·seed)은 결과 객체에서 읽어 결과 헤더 아래에 표시된다(SRS FR-BT-050)
      const runParams = screen.getByTestId("monte-carlo-run-params");
      expect(runParams).toHaveTextContent("실행 설정");
      expect(runParams).toHaveTextContent("21일 블록");
      expect(runParams).toHaveTextContent("seed");
      // 결과 하단에 일상 언어 "쉽게 이해하기" 섹션이 표시된다
      const plainSummary = screen.getByTestId("result-plain-summary");
      expect(plainSummary).toBeInTheDocument();
      expect(plainSummary).not.toHaveClass("rounded-xl");
      expect(plainSummary).not.toHaveClass("border");
      expect(plainSummary).not.toHaveClass("border-white/[0.08]");
      expect(plainSummary).not.toHaveClass("p-4");
      expect(plainSummary).not.toHaveClass("bg-sky-500/[0.05]");
      expect(screen.getByText("쉽게 이해하기")).toHaveClass("text-gray-500");
      // 기본 21일 블록 — 쉬운 해석 첫 문장도 블록 방식을 말한다(2026-09-17 수정 전엔 "무작위로 다시 섞어")
      expect(screen.getByText(/일별 수익률을 21거래일씩 묶어 무작위로 다시 이어 붙여/)).toBeInTheDocument();
      expect(screen.getByText(/30% 넘게 하락한 시나리오는/)).toBeInTheDocument();
      expect(screen.queryByText("위 내용은 모두 과거 데이터 기반 시뮬레이션 결과이며, 미래 수익은 보장되지 않습니다.")).not.toBeInTheDocument();
    });
    // 결과가 나오면 결과 화면으로 넘어가고 설계 화면(캔버스·조정 칸)은 숨는다.
    const resultPage = screen.getByTestId("monte-carlo-result-page");
    expect(resultPage).not.toHaveClass("hidden");
    expect(resultPage).toContainElement(screen.getByTestId("monte-carlo-result-header"));
    expect(screen.getByTestId("validation-lab-controls").closest(".hidden")).not.toBeNull();
    // 재설정하면 결과가 지워지고 설계 화면으로 돌아온다.
    await user.click(within(resultPage).getByRole("button", { name: "재설정" }));
    await waitFor(() => expect(resultPage).toHaveClass("hidden"));
    expect(screen.getByTestId("validation-lab-controls").closest(".hidden")).toBeNull();
    expect(screen.queryByTestId("monte-carlo-result-header")).toBeNull();
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
    await user.click(screen.getByRole("tab", { name: "몬테카를로" }));
    expect(within(optimizationPage).queryByTitle("결과 닫기")).not.toBeInTheDocument();

    // 실행해 결과가 나온 뒤에만 '결과 닫기'가 노출된다.
    await user.click(await screen.findByRole("button", { name: "몬테카를로 실행" }));
    await waitFor(() => {
      expect(screen.getByText("양수 CAGR 확률")).toBeInTheDocument();
    });
    const closeButton = within(optimizationPage).getByTitle("결과 닫기");
    expect(screen.getByTestId("monte-carlo-result-page")).toContainElement(closeButton);

    // 누르기 전까지는 최적화 페이지가 유지되고, 누르면 결과 탭으로 돌아간다.
    expect(screen.getByTestId("backtest-optimization-page")).toBeInTheDocument();
    await user.click(closeButton);
    expect(screen.queryByTestId("backtest-optimization-page")).not.toBeInTheDocument();
    expect(screen.getByTestId("backtest-tab-content")).toBeInTheDocument();
  });

  it("워크포워드 결과는 캔버스가 아니라 따로 보는 결과 화면에 나오고, 재설정하면 설계 화면으로 돌아온다", async () => {
    await renderDashboard("PREMIUM", { onWalkForward: vi.fn() });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    const resultPage = await screen.findByTestId("walk-forward-result-page");
    expect(resultPage).toHaveClass("hidden");

    await user.click(screen.getByRole("button", { name: "(테스트) 결과 만들기" }));
    // 결과가 생기면 결과 화면으로 간다 — 결과는 결과 화면에만 있고, 캔버스에는 결과 판이 없다.
    await waitFor(() => expect(resultPage).not.toHaveClass("hidden"));
    expect(within(resultPage).getByText("워크포워드 결과 본문")).toBeInTheDocument();
    expect(screen.queryByTestId("walk-forward-report-node")).toBeNull();
    expect(screen.getByTestId("validation-lab-controls").closest(".hidden")).not.toBeNull();

    // 결과 화면에는 설계로 돌아가는 버튼이 없다 — 돌아오는 길은 재설정뿐이다.
    expect(within(resultPage).queryByRole("button", { name: "실험 설계로 돌아가기" })).toBeNull();

    // 재설정으로 결과가 사라지면 설계 화면으로 돌아온다.
    await user.click(screen.getByRole("button", { name: "(테스트) 재설정" }));
    await waitFor(() => expect(resultPage).toHaveClass("hidden"));
    expect(screen.queryByRole("button", { name: "결과 보기" })).toBeNull();
  });
});
