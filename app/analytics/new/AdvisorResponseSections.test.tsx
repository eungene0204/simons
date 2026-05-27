import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdvisorResponseSections } from "./AdvisorResponseSections";
import type { AdvisorResult } from "@/components/strategy/StrategyAdvisorPanel";

const SECTION_TITLES = [
  "전략 요약",
  "유사 전략 검색 결과",
  "유사 성공 전략 공통점",
  "유사 실패 전략 공통점",
  "시장 레짐 적합성",
  "리스크 분석",
  "과최적화 가능성",
  "전략 개선 제안",
  "추천 추가 필터",
  "다음 액션",
];

function advisorResultWithSections(): AdvisorResult {
  return {
    strategy_score: 70,
    risk_score: 45,
    overfit_risk: "medium",
    advice: [],
    response_sections: SECTION_TITLES.map((title, index) => ({
      title,
      body: `${title} 본문 ${index + 1}`,
    })),
    suggested_experiments: [],
    ai_model_recommendation: {
      recommended: false,
      reason: "규칙 기반 전략으로 충분합니다.",
    },
  };
}

describe("AdvisorResponseSections", () => {
  it("renders every ordered advisor response section in the chat bubble", () => {
    render(<AdvisorResponseSections result={advisorResultWithSections()} />);

    expect(screen.getByText("전략 리뷰")).toBeInTheDocument();
    expect(screen.getByText("10개 섹션")).toBeInTheDocument();

    for (const title of SECTION_TITLES) {
      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByText(new RegExp(`${title} 본문`))).toBeInTheDocument();
    }
  });

  it("renders nothing when advisor response sections are absent", () => {
    const { container } = render(
      <AdvisorResponseSections
        result={{
          ...advisorResultWithSections(),
          response_sections: [],
        }}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
