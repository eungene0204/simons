import { describe, expect, it } from "vitest";

import { formatCoachAdviceBody, formatPrimaryCoachAdviceBody } from "./advisorCopy";

describe("formatCoachAdviceBody", () => {
  it("removes internal wording while preserving experiment metrics", () => {
    const body =
      "비슷한 31개 실험에서 ma_crossover + max_positions 패턴은 CAGR 중앙값 -2.91%, Sharpe 중앙값 -0.19, MDD 중앙값 -28.39%였습니다. confidence는 high입니다. 비슷한 실험 데이터가 부족합니다. 현재 전략은 추가 백테스트로 먼저 검증하세요. 이 내용은 투자 추천이 아니라 전략 검증/리스크 관리 근거입니다.";

    expect(formatCoachAdviceBody(body)).toBe(
      "비슷한 31개 실험에서 ma_crossover + max_positions 패턴은 CAGR 중앙값 -2.91%, Sharpe 중앙값 -0.19, MDD 중앙값 -28.39%였습니다. 비슷한 실험 데이터가 부족하므로 현재 전략은 추가 백테스트로 먼저 검증하세요."
    );
  });

  it("preserves current experiment evidence and concrete comparison candidates", () => {
    const body =
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 14.28%, Sharpe 중앙값 1.02, MDD 중앙값 -16.71%입니다. 근거 수준은 중간입니다. 우선 비교할 후보는 손절 8% 또는 트레일링 스탑 10% 추가, 익절 15% 또는 트레일링 스탑 추가, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요.";

    expect(formatCoachAdviceBody(body)).toBe(
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 14.28%, Sharpe 중앙값 1.02, MDD 중앙값 -16.71%입니다. 우선 비교할 후보는 손절 8% 또는 트레일링 스탑 10% 추가, 익절 15% 또는 트레일링 스탑 추가, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요."
    );
  });

  it("preserves flat evidence details and do-not-repeat-current-plan warning", () => {
    const body =
      "현재 조건과 가까운 실험군은 CAGR 중앙값 0.00%, Sharpe 중앙값 0.00, MDD 중앙값 0.00%으로 성과 신호가 거의 없었습니다. 근거 수준이 낮아 이 결과만으로 결론을 내리면 안 됩니다. 다음 백테스트에서는 현재안을 그대로 반복하지 말고, 진입 조건 완화, 청산 규칙 추가, 보유기간 제한을 각각 하나씩만 바꿔 비교하세요.";

    expect(formatCoachAdviceBody(body)).toBe(
      "현재 조건과 가까운 실험군은 CAGR 중앙값 0.00%, Sharpe 중앙값 0.00, MDD 중앙값 0.00%으로 성과 신호가 거의 없었습니다. 다음 백테스트에서는 현재안을 그대로 반복하지 말고, 진입 조건 완화, 청산 규칙 추가, 보유기간 제한을 각각 하나씩만 바꿔 비교하세요."
    );
  });

  it("keeps profit factor, trade count, and sample-derived parameter candidates visible", () => {
    const body =
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 9.00%, Sharpe 중앙값 0.80, MDD 중앙값 -12.00%, Profit Factor 중앙값 1.40, 거래 수 중앙값 42회입니다. 근거 수준은 중간입니다. 가까운 샘플도 파라미터가 완전히 같지는 않으므로 후보별 delta만 비교하세요. 우선 비교할 후보는 손절 8% 비교, 익절 15% 비교, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요.";

    expect(formatCoachAdviceBody(body)).toBe(
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 9.00%, Sharpe 중앙값 0.80, MDD 중앙값 -12.00%, Profit Factor 중앙값 1.40, 거래 수 중앙값 42회입니다. 가까운 샘플도 파라미터가 완전히 같지는 않으므로 후보별 delta만 비교하세요. 우선 비교할 후보는 손절 8% 비교, 익절 15% 비교, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요."
    );
  });

  it("formats primary advice as one concise recommendation", () => {
    const body =
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 9.00%, Sharpe 중앙값 0.80, MDD 중앙값 -12.00%, Profit Factor 중앙값 1.40, 거래 수 중앙값 42회입니다. 근거 수준은 중간입니다. 우선 비교할 후보는 손절 8% 비교, 익절 15% 비교, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요.";

    expect(formatPrimaryCoachAdviceBody(body)).toBe(
      "현재 조건과 가까운 실험군의 결과는 CAGR 중앙값 9.00%, Sharpe 중앙값 0.80, MDD 중앙값 -12.00%, Profit Factor 중앙값 1.40, 거래 수 중앙값 42회입니다. 우선 비교할 후보는 손절 8% 비교, 익절 15% 비교, 최대 보유기간 20일 비교입니다. 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요."
    );
  });

  it("keeps the full new experiment advice instead of splitting decimal metrics", () => {
    const body =
      "제안 주신 전략과 비슷한 전략의 결과가 CAGR 중앙값 4.80%, Sharpe 중앙값 0.95, MDD 중앙값 -16.77%로 나왔습니다. 손절은 12%, 최대 보유기간은 10일, 보유 종목 수는 20개로 각각 바꿔 테스트해 보세요. 테스트 후에는 MDD와 Sharpe가 동시에 좋아지는 설정만 남기세요.";

    expect(formatPrimaryCoachAdviceBody(body)).toBe(
      "입력 하신 전략과 비슷한 전략으로 테스트 해본 결과 CAGR 중앙값 4.80%, Sharpe 중앙값 0.95, MDD 중앙값 -16.77%로 나왔습니다. 손절은 12%, 최대 보유기간은 10일, 보유 종목 수는 20개로 각각 바꿔 테스트해 보세요. 테스트 후에는 MDD와 Sharpe가 동시에 좋아지는 설정만 남기세요."
    );
  });

  it("rewrites low-sample experiment guidance into a plain warning", () => {
    const body = "실험 샘플이 부족해 확신하기 어렵습니다. 유사 실험의 중앙값 성과를 기준으로 리스크 설정을 비교하세요.";

    expect(formatCoachAdviceBody(body)).toBe(
      "지금 전략은 근거가 부족합니다. 기본안을 먼저 돌린 뒤 손절, 보유기간, 종목 수 조건을 하나씩만 바꿔 비교하세요."
    );
  });

  it("rewrites experience memory copy into an actionable experiment suggestion", () => {
    const body =
      "유사 전략 5건의 Experience Memory를 확인했습니다. 재사용 가능한 핵심 교훈은 'ChromaDB에서 검색된 과거 백테스트 사례입니다. result_status=FAIL, similarity=0.404. 동일 조건 재백테스트와 OOS 검증 전에는 성과를 확정하지 않습니다.'입니다. 이 근거는 투자 추천이 아니라 현재 전략의 개선 후보를 재백테스트하기 위한 비교 기준입니다.";

    expect(formatCoachAdviceBody(body)).toBe(
      "기본안을 그대로 돌린 뒤, 손절 8~10%, 최대 보유기간 20일, 종목 수 5~10개 분산안을 각각 비교해 어느 조건이 손실을 줄이는지 먼저 확인하세요."
    );
  });
});
