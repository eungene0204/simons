import { describe, expect, it } from "vitest";
import { runButtonPlacement } from "./runButtonPlacement";

describe("runButtonPlacement", () => {
  it("검증 텍스트가 없으면 전략 요약 아래에만 버튼을 둔다", () => {
    expect(runButtonPlacement({})).toBe("summary");
  });

  it("검증 텍스트가 도착하면 검증 블록 아래로만 버튼이 이동한다 (중복 렌더 회귀)", () => {
    // 회귀: coachText가 있어도 요약 아래 버튼이 남아 '백테스트 실행'이 두 개 보였다.
    expect(runButtonPlacement({ coachText: "전략 정의가 완료되었습니다." })).toBe("coach");
  });

  it("검증 생성 중에는 버튼을 숨긴다", () => {
    expect(runButtonPlacement({ coachLoading: true, coachText: "" })).toBe(null);
  });

  it("명확화 질문이 남아 있으면 버튼을 숨긴다", () => {
    expect(runButtonPlacement({ clarification: "어떤 시장을 대상으로 할까요?" })).toBe(null);
  });

  it("명확화 질문이 있어도 검증이 끝났으면 검증 아래에 버튼을 둔다 (기존 동작 보존)", () => {
    expect(
      runButtonPlacement({ coachText: "검증 완료", clarification: "추가 질문" })
    ).toBe("coach");
  });
});
