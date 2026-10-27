import { describe, expect, it } from "vitest";
import { isExecutableStrategy, pickExecutedRequest, resolveStrategyToSave } from "./executableRequest";

// 2026-10-27 사고: 결과 화면이 실행 설정 없이 '저장'을 보내면 `dsl ?? {}`로 빈 설정이 저장돼
// 이름·설명만 남은 전략(다시 실행·전략 시뮬레이션 불가)이 생겼다.
const EXECUTABLE = {
  universe_id: "kospi200",
  entry: { conditions: [{ type: "filter", id: "pbr", params: { operator: "<=", value: 1 } }] },
  exit: { conditions: [] },
  risk: { max_positions: 10 },
};

describe("저장 가능한(다시 실행할 수 있는) 전략 설정", () => {
  it("entry·exit·risk가 있어야 실행 가능하다", () => {
    expect(isExecutableStrategy(EXECUTABLE)).toBe(true);
    expect(isExecutableStrategy({})).toBe(false);
    expect(isExecutableStrategy({ id: "x", name: "이름", description: "설명", updated_at: "t" })).toBe(false);
    expect(isExecutableStrategy({ entry_signals: [], exit_signals: [] })).toBe(false);
    expect(isExecutableStrategy(null)).toBe(false);
    expect(pickExecutedRequest({ ...EXECUTABLE, name: "표시용" })).not.toHaveProperty("name");
  });

  it("화면 DSL이 실행 가능하면 그것을 쓴다", () => {
    expect(resolveStrategyToSave(EXECUTABLE, { executedRequest: { other: 1 } })).toBe(EXECUTABLE);
  });

  it("화면 DSL이 없거나 비어 있으면 결과에 동봉된 실행 요청을 쓴다", () => {
    expect(resolveStrategyToSave(null, { executedRequest: EXECUTABLE })).toBe(EXECUTABLE);
    expect(resolveStrategyToSave({}, { executedRequest: EXECUTABLE })).toBe(EXECUTABLE);
  });

  it("둘 다 없으면 null — 빈 설정으로 대신 저장하지 않는다", () => {
    expect(resolveStrategyToSave(null, null)).toBeNull();
    expect(resolveStrategyToSave({}, { executedRequest: {} })).toBeNull();
  });
});
