import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriceRow } from "@/components/order/PriceRow";

const formatPrice = (p: number) => p.toLocaleString("ko-KR");

describe("PriceRow", () => {
  it("매수(bid) 행의 가격은 현재가가 닿아도 항상 빨간색 톤을 유지한다", () => {
    // 전일 종가 대비 -5% 하락 상황에서 매수 호가에 체결이 들어와도
    // 가격이 파란색으로 뒤집히면 안 된다 (한국 호가창 표준).
    render(
      <PriceRow
        price={9500}
        changePct={-5}
        side="bid"
        isCurrent
        formatPrice={formatPrice}
      />
    );

    const priceCell = screen.getByText("9,500");
    expect(priceCell.className).toContain("text-red-400");
    expect(priceCell.className).not.toContain("text-blue-400");
  });

  it("매도(ask) 행의 가격은 현재가가 닿아도 항상 파란색 톤을 유지한다", () => {
    render(
      <PriceRow
        price={10500}
        changePct={5}
        side="ask"
        isCurrent
        formatPrice={formatPrice}
      />
    );

    const priceCell = screen.getByText("10,500");
    expect(priceCell.className).toContain("text-blue-400");
    expect(priceCell.className).not.toContain("text-red-400");
  });
});
