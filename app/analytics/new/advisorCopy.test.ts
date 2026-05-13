import { describe, expect, it } from "vitest";

import { formatCoachAdviceBody, formatCoachAdviceTitle } from "./advisorCopy";

describe("formatCoachAdviceBody", () => {
  it("rewrites experiment evidence copy into a short user-facing summary", () => {
    const body =
      "비슷한 31개 실험에서 ma_crossover + max_positions 패턴은 CAGR 중앙값 -2.91%, Sharpe 중앙값 -0.19, MDD 중앙값 -28.39%였습니다. confidence는 high입니다. 비슷한 실험 데이터가 부족합니다. 현재 전략은 추가 백테스트로 먼저 검증하세요. 이 내용은 투자 추천이 아니라 전략 검증/리스크 관리 근거입니다.";

    expect(formatCoachAdviceBody(body)).toBe(
      "유사한 전략 실험 31건을 보면 수익성은 낮고 손실 폭은 큰 편이었습니다. 지금 전략은 바로 사용하기보다 추가 백테스트로 먼저 검증하는 편이 안전합니다."
    );
  });

  it("rewrites low-sample experiment guidance into a plain warning", () => {
    const body = "실험 샘플이 부족해 확신하기 어렵습니다. 유사 실험의 중앙값 성과를 기준으로 리스크 설정을 비교하세요.";

    expect(formatCoachAdviceBody(body)).toBe(
      "유사 사례가 충분하지 않아, 지금 전략은 바로 사용하기보다 추가 백테스트로 먼저 검증하는 편이 안전합니다."
    );
  });

  it("rewrites experience memory copy into an actionable experiment suggestion", () => {
    const body =
      "유사 전략 5건의 Experience Memory를 확인했습니다. 재사용 가능한 핵심 교훈은 'ChromaDB에서 검색된 과거 백테스트 사례입니다. result_status=FAIL, similarity=0.404. 동일 조건 재백테스트와 OOS 검증 전에는 성과를 확정하지 않습니다.'입니다. 이 근거는 투자 추천이 아니라 현재 전략의 개선 후보를 재백테스트하기 위한 비교 기준입니다.";

    expect(formatCoachAdviceTitle("유사 전략 경험 기반 점검")).toBe("비교 실험 제안");
    expect(formatCoachAdviceBody(body)).toBe(
      "비슷한 과거 전략은 성과가 불안정했습니다. 기본안을 그대로 돌린 뒤, 손절 8~10%, 최대 보유기간 20일, 종목 수 5~10개 분산안을 각각 비교해 어느 조건이 손실을 줄이는지 먼저 확인하세요."
    );
  });
});
