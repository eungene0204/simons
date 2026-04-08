import { describe, expect, it } from "vitest";
import { getStaticVIPrices } from "@/lib/vi-price";

describe("getStaticVIPrices", () => {
  it("정적 VI는 기준가격 대비 ±10%를 호가단위에 맞춰 계산해야 한다", () => {
    expect(getStaticVIPrices(3620)).toEqual({
      upVI: 3985,
      downVI: 3255,
      rate: 0.1,
    });
  });

  it("갭 상승 종목은 시가 기준가격을 넣으면 HTS 표시값과 동일해야 한다", () => {
    expect(getStaticVIPrices(3620)).toEqual({
      upVI: 3985,
      downVI: 3255,
      rate: 0.1,
    });
  });
});
