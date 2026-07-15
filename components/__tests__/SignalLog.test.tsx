import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SignalLog from "@/components/virtual-market/SignalLog";

const daysAgo = (n: number) =>
  new Date(Date.now() - n * 86_400_000).toISOString();

describe("SignalLog 빈 상태", () => {
  it("신호가 없고 개설 3일 미만이면 기본 안내를 표시한다", () => {
    render(<SignalLog logs={[]} accountCreatedAt={daysAgo(1)} onStrategyReplace={vi.fn()} />);
    expect(screen.getByText("아직 시그널이 발생하지 않았습니다.")).toBeInTheDocument();
    expect(screen.queryByText("다른 전략으로 교체하기")).not.toBeInTheDocument();
  });

  it("신호가 없고 3일 이상 경과하면 경과일 안내와 교체 버튼을 표시한다", () => {
    render(<SignalLog logs={[]} accountCreatedAt={daysAgo(3)} onStrategyReplace={vi.fn()} />);
    expect(
      screen.getByText("최근 3일간 이 전략의 매매 신호가 발생하지 않았습니다.")
    ).toBeInTheDocument();
    expect(screen.getByText("다른 전략으로 교체하기")).toBeInTheDocument();
  });

  it("교체 버튼 클릭 시 onStrategyReplace를 호출한다", () => {
    const onStrategyReplace = vi.fn();
    render(<SignalLog logs={[]} accountCreatedAt={daysAgo(5)} onStrategyReplace={onStrategyReplace} />);
    fireEvent.click(screen.getByText("다른 전략으로 교체하기"));
    expect(onStrategyReplace).toHaveBeenCalledOnce();
  });

  it("경과일 정보가 없으면 기본 안내를 표시한다", () => {
    render(<SignalLog logs={[]} />);
    expect(screen.getByText("아직 시그널이 발생하지 않았습니다.")).toBeInTheDocument();
  });
});
