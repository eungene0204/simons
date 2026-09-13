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

describe("SignalLog 사유·가격 표기", () => {
  // 사고(2026-09-13): 백엔드 자동매매가 VirtualMarketLog.reason에 엔진의 세그먼트 페이로드
  // (\u001eRJ + JSON)를 그대로 저장했는데 카드가 그 문자열을 찍어 코드가 노출됐다.
  const encoded =
    "\u001eRJ" +
    JSON.stringify([
      { t: "종가가 {0}일선 상향 돌파", a: [60] },
      { s: " + " },
      { t: "RSI {0} {1}", a: [40, { t: "이하" }] },
    ]);
  const log = {
    id: "l1",
    accountId: "a1",
    date: "2026-09-11",
    symbol: "DASH",
    stockName: "DoorDash",
    signalType: "entry" as const,
    reason: encoded,
    price: 202.55,
    action: "notified" as const,
    orderId: null,
    createdAt: "2026-09-11T00:00:00Z",
  };

  it("인코딩된 세그먼트 사유를 문장으로 렌더링한다(원문 JSON 노출 금지)", () => {
    render(<SignalLog logs={[log]} />);
    expect(screen.getByText(/종가가 60일선 상향 돌파 \+ RSI 40 이하/)).toBeInTheDocument();
    expect(screen.queryByText(/RJ\[/)).not.toBeInTheDocument();
  });

  it("평문 사유(구버전 로그)는 그대로 표시한다", () => {
    render(<SignalLog logs={[{ ...log, reason: "손절매 실행" }]} />);
    expect(screen.getByText(/손절매 실행/)).toBeInTheDocument();
  });

  it("USD 계좌는 가격을 달러 소수점으로 표기한다", () => {
    render(<SignalLog logs={[log]} currency="USD" />);
    expect(screen.getByText("$202.55")).toBeInTheDocument();
    expect(screen.queryByText(/원/)).not.toBeInTheDocument();
  });

  it("KRW 계좌(기본)는 원 표기를 유지한다", () => {
    render(<SignalLog logs={[{ ...log, price: 71200 }]} />);
    expect(screen.getByText("71,200원")).toBeInTheDocument();
  });
});
