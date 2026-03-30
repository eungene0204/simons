import { describe, it, expect } from "vitest";
import { inferStrategyType } from "@/lib/strategy-type";

describe("inferStrategyType", () => {
  // DSL 기반 판정
  it("AI 모델 조건 → AI전략", () => {
    const dsl = { entry: { conditions: [{ id: "ai_model", type: "indicator" }] } };
    expect(inferStrategyType("전략1", "", dsl)).toBe("AI전략");
  });

  it("ai_drop_model 조건 → AI전략", () => {
    const dsl = { entry: { conditions: [{ id: "ai_drop_model", type: "indicator" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("AI전략");
  });

  it("per 필터 → 가치투자", () => {
    const dsl = { entry: { conditions: [{ id: "per", type: "filter" }] } };
    expect(inferStrategyType("저PBR 전략", "", dsl)).toBe("가치투자");
  });

  it("pbr/roe 조건 → 가치투자", () => {
    const dsl = { entry: { conditions: [{ id: "pbr" }, { id: "roe" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("가치투자");
  });

  it("investor_net_buy 조건 → 수급전략", () => {
    const dsl = { entry: { conditions: [{ id: "investor_net_buy" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("수급전략");
  });

  it("breakout 조건 → 모멘텀", () => {
    const dsl = { entry: { conditions: [{ id: "breakout" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("모멘텀");
  });

  it("ma_crossover 조건 → 모멘텀", () => {
    const dsl = { entry: { conditions: [{ id: "ma_crossover" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("모멘텀");
  });

  it("rsi 조건 → 기술분석", () => {
    const dsl = { entry: { conditions: [{ id: "rsi" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("기술분석");
  });

  it("bollinger_bands 조건 → 기술분석", () => {
    const dsl = { exit: { conditions: [{ id: "bollinger_bands" }] } };
    expect(inferStrategyType("", "", dsl)).toBe("기술분석");
  });

  // 텍스트 기반 판정 (DSL 조건 없을 때)
  it("이름에 '가치' → 가치투자", () => {
    expect(inferStrategyType("가치투자 전략", "", {})).toBe("가치투자");
  });

  it("이름에 '모멘텀' → 모멘텀", () => {
    expect(inferStrategyType("모멘텀 전략", "", {})).toBe("모멘텀");
  });

  it("이름에 'AI' → AI전략", () => {
    expect(inferStrategyType("AI 예측 전략", "", {})).toBe("AI전략");
  });

  it("설명에 '외국인 순매수' → 수급전략", () => {
    expect(inferStrategyType("전략A", "외국인 순매수 기반", {})).toBe("수급전략");
  });

  it("설명에 'RSI' → 기술분석", () => {
    expect(inferStrategyType("전략A", "RSI 과매도 진입", {})).toBe("기술분석");
  });

  it("아무 정보 없음 → 기타", () => {
    expect(inferStrategyType("", "", {})).toBe("기타");
  });

  // DSL이 텍스트보다 우선
  it("DSL에 ai_model 있으면 텍스트 '가치' 보다 우선 → AI전략", () => {
    const dsl = { entry: { conditions: [{ id: "ai_model" }] } };
    expect(inferStrategyType("가치 AI 전략", "가치 기반", dsl)).toBe("AI전략");
  });
});
