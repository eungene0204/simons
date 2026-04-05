/**
 * 개발 서버 설정 회귀 테스트
 *
 * 버그 이력:
 * - uvicorn --reload를 --reload-dir 없이 실행하면 node_modules(10만+파일) 포함
 *   프로젝트 전체를 StatReload(폴링)로 감시 → 아이들 CPU 62~90% 상시 소비.
 *   이 상태에서 백테스트 ThreadPoolExecutor가 CPU-bound 작업을 하면 OS 레벨 경쟁으로
 *   KOSPI200 백테스트가 4초 → 65초로 폭증.
 *   수정: --reload-dir backend 추가 → backend/ 디렉토리(~50개 파일)만 감시.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

const pkg = JSON.parse(
  readFileSync(resolve(__dirname, "../package.json"), "utf-8")
);

describe("dev:backend 스크립트 설정", () => {
  const script: string = pkg.scripts?.["dev:backend"] ?? "";

  it("--reload 플래그가 포함되어야 한다", () => {
    expect(script).toContain("--reload");
  });

  it("--reload-dir backend가 포함되어야 한다 (전체 파일 폴링 방지)", () => {
    // --reload-dir 없이 --reload만 쓰면 프로젝트 루트 전체(node_modules 포함)를
    // StatReload로 폴링하여 아이들 CPU 62~90% → 백테스트 65초 지연 재현
    expect(script).toContain("--reload-dir backend");
  });

  it("--reload-dir가 backend/ 디렉토리를 가리켜야 한다 (node_modules 제외)", () => {
    // node_modules(~10만 파일)나 data/(~4천 파일)를 감시하면 안 됨
    expect(script).not.toMatch(/--reload-dir\s+\./);        // 루트 전체 감시 금지
    expect(script).not.toMatch(/--reload-dir\s+node_modules/);
  });
});
