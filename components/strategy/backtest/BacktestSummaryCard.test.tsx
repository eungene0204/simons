import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BacktestSummaryCard from "./BacktestSummaryCard";
import type { AiReportData } from "./aiReport";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const baseResult = {
  cacheKey: "ck-1",
  cagr: 12,
  profitFactor: 1.8,
  maxDrawdown: 14,
  sharpe: 1.1,
  calmar: 0.9,
  equity: [100, 101, 102, 103],
} as any;

// 전략 검증 전문가 리포트(10섹션) 전체 필드를 갖춘 리포트.
const fullReport: AiReportData = {
  summary: "핵심 요약 문단입니다.",
  score: 80,
  strengths: ["강점 항목"],
  weaknesses: ["약점 항목"],
  improvements: ["추가 검증을 먼저 수행하십시오."],
  advisorScore: 80,
  riskScore: 35,
  overfitRisk: "low",
  topInsights: ["수익이 특정 기간에 집중되었습니다."],
  hiddenRisks: ["소수 종목에 성과가 의존합니다."],
  overfittingAnalysis: "거래 표본이 적어 과최적화 가능성이 있습니다.",
  strategyProfile: ["평균회귀형", "고회전"],
  strategyProfileNote: "특정 국면에서만 강하게 작동했습니다.",
  validationRoadmap: [
    { title: "몬테카를로 시뮬레이션", reason: "표본이 적기 때문입니다.", priority: 1 },
  ],
  finalVerdict: "현 시점에서는 추가 검증이 필요합니다.",
};

describe("BacktestSummaryCard 전략 검증 전문가 리포트", () => {
  it("리스크 진단과 10섹션 핵심 영역을 렌더한다", () => {
    render(<BacktestSummaryCard result={baseResult} initialReport={fullReport} />);

    // 헤더 유지
    expect(screen.getByText("리스크 점수")).toBeInTheDocument();
    expect(screen.getByText("과적합 위험")).toBeInTheDocument();

    // 항상 펼쳐지는 핵심 섹션
    expect(screen.getByText("핵심 요약")).toBeInTheDocument();
    expect(screen.getByText("핵심 통찰")).toBeInTheDocument();
    expect(screen.getByText("숨은 위험")).toBeInTheDocument();
    expect(screen.getByText("최종 평가")).toBeInTheDocument();
    expect(screen.getByText("수익이 특정 기간에 집중되었습니다.")).toBeInTheDocument();
    expect(screen.getByText("현 시점에서는 추가 검증이 필요합니다.")).toBeInTheDocument();

    // 접힘 섹션 헤더는 존재
    expect(screen.getByText("검증 로드맵")).toBeInTheDocument();
    expect(screen.getByText("전략 성향")).toBeInTheDocument();
    expect(screen.getByText("개선 우선순위")).toBeInTheDocument();
  });

  it("접힌 섹션은 클릭 시 내용을 펼친다", async () => {
    const user = userEvent.setup();
    render(<BacktestSummaryCard result={baseResult} initialReport={fullReport} />);

    // 검증 로드맵 항목은 접혀 있어 처음엔 보이지 않는다.
    expect(screen.queryByText("몬테카를로 시뮬레이션")).toBeNull();
    await user.click(screen.getByText("검증 로드맵"));
    expect(screen.getByText("몬테카를로 시뮬레이션")).toBeInTheDocument();
  });

  it("구 저장 리포트(확장 필드 없음)도 깨지지 않고 핵심 요약을 렌더한다", () => {
    const legacyReport: AiReportData = {
      summary: "구 총평",
      score: 62,
      strengths: ["장점"],
      weaknesses: ["단점"],
      improvements: ["개선점"],
      advisorScore: 60,
      riskScore: 40,
      overfitRisk: "medium",
    };
    render(<BacktestSummaryCard result={baseResult} initialReport={legacyReport} />);

    expect(screen.getByText("핵심 요약")).toBeInTheDocument();
    expect(screen.getByText("구 총평")).toBeInTheDocument();
    // 확장 섹션은 데이터가 없으면 렌더하지 않는다.
    expect(screen.queryByText("핵심 통찰")).toBeNull();
    expect(screen.queryByText("숨은 위험")).toBeNull();
    expect(screen.queryByText("최종 평가")).toBeNull();
    // 개선 우선순위는 improvements 폴백으로 유지된다.
    expect(screen.getByText("개선 우선순위")).toBeInTheDocument();
  });

  it("점수 설명 툴팁을 유지한다", () => {
    render(<BacktestSummaryCard result={baseResult} initialReport={fullReport} />);
    expect(screen.getAllByRole("button", { name: /점수 설명/ })).toHaveLength(3);
  });
});
