import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import TrackedSymbolRow from "@/components/virtual-account/TrackedSymbolRow";

describe("TrackedSymbolRow", () => {
  it("종목명 왼쪽에 별도 번호/배지를 표시하지 않아야 함", () => {
    render(
      <TrackedSymbolRow
        symbol="005930"
        name="삼성전자"
        quote={{ price: 70000, changePercent: 1.23, volume: 123456 }}
        hasHolding={false}
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        formatPrice={(price) => new Intl.NumberFormat("ko-KR").format(price)}
      />
    );

    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("005930")).toBeInTheDocument();
    expect(screen.getByText("70,000")).toBeInTheDocument();
    expect(screen.queryByText("00")).not.toBeInTheDocument();
  });
});
