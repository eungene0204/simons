import { describe, expect, it } from "vitest";
import { isResultOwnerMismatch, parseResultOwner, stripResultOwner } from "./resultOwner";

// 2026-09-22 guest_1656 사고: 다른 계정으로 받은 결과 화면에서 게스트 이름의 전략·계좌가 생겼다.
describe("resultOwner", () => {
  it("주인과 지금 계정이 다르면 불일치", () => {
    expect(isResultOwnerMismatch(2, 31)).toBe(true);
    expect(isResultOwnerMismatch(31, 31)).toBe(false);
  });

  it("주인을 모르는 옛 결과는 막지 않는다", () => {
    expect(isResultOwnerMismatch(undefined, 31)).toBe(false);
    expect(isResultOwnerMismatch("2", 31)).toBe(false);
  });

  it("헤더 값을 정수 id로 읽는다", () => {
    expect(parseResultOwner("42")).toBe(42);
    expect(parseResultOwner(null)).toBeUndefined();
    expect(parseResultOwner("")).toBeUndefined();
    expect(parseResultOwner("abc")).toBeUndefined();
  });

  it("저장 전에 주인 표시를 뗀다", () => {
    expect(stripResultOwner({ totalReturn: 1, ownerUserId: 2 })).toEqual({ totalReturn: 1 });
    expect(stripResultOwner(undefined)).toBeUndefined();
  });
});
