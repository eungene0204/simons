// @ts-nocheck
/**
 * /api/strategy GET 핸들러의 전략 변환 로직 회귀 테스트
 *
 * 버그 수정 이력:
 * - settings JSON의 id 필드가 DB id와 다를 수 있어서 가상계좌 생성 시
 *   전략을 선택해도 selectedStrategyId가 빈 값이 되는 문제 수정
 * - 수정 후: DB의 id 값이 항상 settings.id를 덮어쓰도록 변경
 */
import { describe, it, expect } from "vitest";

// /api/strategy route.ts GET 핸들러의 변환 로직
function buildStrategyList(
  dbRows: Array<{ id: string; settings: string }>
): Array<Record<string, unknown>> {
  return dbRows.map((s) => ({
    ...JSON.parse(s.settings),
    id: s.id,
  }));
}

// ── 픽스처 ──────────────────────────────────────────────────────────────────

const dbRowWithMatchingId = {
  id: "db-id-001",
  settings: JSON.stringify({ id: "db-id-001", name: "전략A" }),
};

const dbRowWithMismatchedId = {
  id: "db-id-002",
  settings: JSON.stringify({ id: "old-settings-id", name: "전략B" }),
};

const dbRowWithNoIdInSettings = {
  id: "db-id-003",
  settings: JSON.stringify({ name: "전략C" }),
};

// ── 테스트 ──────────────────────────────────────────────────────────────────

describe("buildStrategyList (GET /api/strategy)", () => {
  it("settings.id와 DB id가 같으면 id가 그대로 반환되어야 함", () => {
    const result = buildStrategyList([dbRowWithMatchingId]);
    expect(result[0].id).toBe("db-id-001");
  });

  it("settings.id와 DB id가 다를 때 DB id를 사용해야 함 (버그 수정)", () => {
    const result = buildStrategyList([dbRowWithMismatchedId]);
    expect(result[0].id).toBe("db-id-002");
    expect(result[0].id).not.toBe("old-settings-id");
  });

  it("settings에 id 필드가 없어도 DB id가 올바르게 주입되어야 함", () => {
    const result = buildStrategyList([dbRowWithNoIdInSettings]);
    expect(result[0].id).toBe("db-id-003");
  });

  it("settings의 나머지 필드(name 등)는 보존되어야 함", () => {
    const result = buildStrategyList([dbRowWithMismatchedId]);
    expect(result[0].name).toBe("전략B");
  });

  it("여러 전략이 있을 때 각각 올바른 DB id를 가져야 함", () => {
    const result = buildStrategyList([
      dbRowWithMatchingId,
      dbRowWithMismatchedId,
      dbRowWithNoIdInSettings,
    ]);
    expect(result).toHaveLength(3);
    expect(result[0].id).toBe("db-id-001");
    expect(result[1].id).toBe("db-id-002");
    expect(result[2].id).toBe("db-id-003");
  });

  it("빈 배열이 입력되면 빈 배열을 반환해야 함", () => {
    expect(buildStrategyList([])).toEqual([]);
  });

  it("반환된 id는 항상 truthy여야 함 (CreateAccountModal 전략 선택 조건)", () => {
    const result = buildStrategyList([
      dbRowWithMatchingId,
      dbRowWithMismatchedId,
      dbRowWithNoIdInSettings,
    ]);
    result.forEach((s) => {
      expect(s.id).toBeTruthy();
    });
  });
});
