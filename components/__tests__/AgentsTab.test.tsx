// @ts-nocheck
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import AgentsTab from "../admin/AgentsTab";

// 운영 콘솔 Agents 탭 — agent별 서브탭 전환과 흐름도(노드·분기) 렌더링을 검증한다.
// 데이터는 정적 스냅샷이므로 API 목킹이 필요 없다.

describe("AgentsTab", () => {
  it("agent 서브탭 목록과 기본 선택(전략 해석기)을 렌더링한다", () => {
    render(<AgentsTab />);

    for (const name of [
      "전략 해석기",
      "대화 플래너",
      "질문 분류기",
      "전략 빌더",
      "전략 수정기",
      "전략 검증 도우미",
      "AI 리포트",
      "테마 학습기",
      "종목 질문 도우미",
    ]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }

    // 기본 선택 agent의 흐름도 노드가 보인다
    expect(screen.getByText("AI 의미 해석")).toBeTruthy();
    expect(screen.getByText("규제 안전 게이트")).toBeTruthy();
  });

  it("서브탭을 누르면 해당 agent의 흐름도로 전환된다", () => {
    render(<AgentsTab />);

    fireEvent.click(screen.getByRole("button", { name: "전략 수정기" }));
    expect(screen.getByText("환각 방지 게이트")).toBeTruthy();
    // 이전 agent의 노드는 사라진다
    expect(screen.queryByText("AI 의미 해석")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "테마 학습기" }));
    expect(screen.getByText("어휘집 캐시 조회")).toBeTruthy();
  });

  it("분기 흐름(성공/되묻기)을 라벨과 함께 렌더링한다", () => {
    render(<AgentsTab />);

    // 전략 해석기의 분기 라벨
    expect(screen.getByText("빠진 조건이 있으면")).toBeTruthy();
    expect(screen.getByText("완성이면")).toBeTruthy();
    expect(screen.getByText("되묻기 + 추천값 칩")).toBeTruthy();
  });
});
