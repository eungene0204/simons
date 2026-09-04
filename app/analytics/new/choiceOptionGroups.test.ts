import { describe, expect, it } from "vitest";

import { groupChoiceOptions } from "./choiceOptionGroups";

const FREE_INPUT = "직접 입력";

// 백엔드 정본(engine/strategy_slots.py ENTRY)의 매수 칩 아홉 개 + 빌더 레인이 붙이는 '직접 입력'.
const ENTRY_CHIPS = [
  "골든크로스(5일/20일) 발생 시 매수",
  "RSI 30 이하에서 매수",
  "MACD 골든크로스 매수",
  "볼린저밴드 하단 터치 시 매수",
  "20일 고점 돌파 시 매수",
  "거래량 급증 시 매수",
  "최근 3개월 수익률 상위 매수",
  "PER 10 이하",
  "ROE 15% 이상",
  FREE_INPUT,
];

describe("선택 칩 묶음", () => {
  it("매수 조건 칩을 시점 신호·순위·필터 세 묶음으로 가른다", () => {
    const grouped = groupChoiceOptions(ENTRY_CHIPS, FREE_INPUT);
    expect(grouped?.groups).toEqual([
      {
        title: "매수 시점 신호",
        options: ENTRY_CHIPS.slice(0, 6),
      },
      { title: "순위로 담기", options: ["최근 3개월 수익률 상위 매수"] },
      { title: "종목 필터", options: ["PER 10 이하", "ROE 15% 이상"] },
    ]);
    // '직접 입력' 칩은 묶음에 들어가지 않는다 — 묶인 목록은 입력창을 위에 연 채로 둔다.
    expect(grouped?.groups.flatMap((group) => group.options)).not.toContain(FREE_INPUT);
    expect(grouped?.placeholder).toBe("원하는 매수 조건을 직접 적어 주세요");
    expect(grouped?.note).toContain("함께 쓸 수 있어요");
  });

  it("묶음이 하나만 드러나면 묶지 않는다(소제목 하나는 소음이다)", () => {
    expect(groupChoiceOptions(ENTRY_CHIPS.slice(0, 6), FREE_INPUT)).toBeNull();
    expect(groupChoiceOptions(["PER 10 이하", "ROE 15% 이상", FREE_INPUT], FREE_INPUT)).toBeNull();
  });

  it("묶음 정본에 없는 목록(매도 조건 등)은 평평한 목록으로 남긴다", () => {
    expect(
      groupChoiceOptions(
        ["데드크로스(5일/20일) 발생 시 매도", "RSI 70 이상에서 매도", "20일 보유 후 청산", FREE_INPUT],
        FREE_INPUT,
      ),
    ).toBeNull();
    expect(groupChoiceOptions(["최대 5종목", "최대 10종목"], FREE_INPUT)).toBeNull();
  });

  it("어느 묶음에도 없는 칩은 제목 없는 꼬리 묶음으로 남겨 잃지 않는다", () => {
    const grouped = groupChoiceOptions(
      ["RSI 30 이하에서 매수", "PER 10 이하", "삼성전자 관련주", FREE_INPUT],
      FREE_INPUT,
    );
    expect(grouped?.groups.map((group) => group.title)).toEqual(["매수 시점 신호", "종목 필터", ""]);
    expect(grouped?.groups.at(-1)?.options).toEqual(["삼성전자 관련주"]);
  });
});
