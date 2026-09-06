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

  it("매도 조건 칩을 시점 신호와 기간 청산으로 가른다", () => {
    const grouped = groupChoiceOptions(
      [
        "데드크로스(5일/20일) 발생 시 매도",
        "RSI 70 이상에서 매도",
        "MACD 데드크로스 매도",
        "볼린저밴드 상단 터치 시 매도",
        "20일 저점 이탈 시 매도",
        "20일 보유 후 청산",
        FREE_INPUT,
      ],
      FREE_INPUT,
    );
    expect(grouped?.groups.map((group) => group.title)).toEqual([
      "매도 시점 신호",
      "기간으로 청산",
    ]);
    expect(grouped?.groups.at(-1)?.options).toEqual(["20일 보유 후 청산"]);
    expect(grouped?.placeholder).toBe("원하는 매도 조건을 직접 적어 주세요");
  });

  // 값/거부가 갈리는 목록(리밸런싱·손절·익절·기간)은 두 묶음, 한 축의 값만 있는 목록
  // (최대 보유·초기 자본·리밸런싱 방식)은 제목 없이 평평하게 — 소제목 하나는 소음이다.
  it.each([
    {
      name: "리밸런싱",
      options: ["매주 리밸런싱", "매월 리밸런싱", "분기마다 리밸런싱", "리밸런싱 안 함"],
      titles: ["정해진 주기마다", "사용 안 함"],
      placeholder: "원하는 리밸런싱 주기를 직접 적어 주세요",
    },
    {
      name: "손절",
      options: ["손절 -5%", "손절 -10%", "손절 -15%", "손절 안 함"],
      titles: ["손절 폭", "사용 안 함"],
      placeholder: "원하는 손절 기준을 직접 적어 주세요",
    },
    {
      name: "익절",
      options: ["익절 10%", "익절 20%", "익절 30%", "익절 안 함"],
      titles: ["익절 폭", "사용 안 함"],
      placeholder: "원하는 익절 기준을 직접 적어 주세요",
    },
    {
      name: "백테스트 기간",
      options: [
        "최근 1년 데이터",
        "최근 3년 데이터",
        "최근 5년 데이터",
        "사용 가능한 전체 데이터",
      ],
      titles: ["최근 기간", "전체 기간"],
      placeholder: "원하는 백테스트 기간을 직접 적어 주세요",
    },
    {
      name: "최대 보유",
      options: ["최대 5종목", "최대 10종목", "최대 20종목"],
      titles: [""],
      placeholder: "원하는 종목 수를 직접 적어 주세요",
    },
    {
      name: "분위 그룹 최대 보유",
      options: ["그룹당 10종목", "그룹당 20종목", "그룹당 30종목"],
      titles: [""],
      placeholder: "그룹당 담을 종목 수를 직접 적어 주세요",
    },
    {
      name: "랭킹 최대 보유",
      options: ["상위 5종목", "상위 10종목", "상위 20종목"],
      titles: [""],
      placeholder: "보유할 상위 종목 수를 직접 적어 주세요",
    },
    {
      name: "초기 자본",
      options: ["500만원", "1,000만원", "3,000만원", "5,000만원"],
      titles: [""],
      placeholder: "원하는 초기 자금을 직접 적어 주세요",
    },
    {
      name: "초기 자본(미국)",
      options: ["$10,000", "$30,000", "$50,000", "$100,000"],
      titles: [""],
      placeholder: "원하는 초기 자금을 직접 적어 주세요",
    },
  ])("$name 목록은 입력창 문구를 갖고 칩 순서는 그대로다", ({ options, titles, placeholder }) => {
    const grouped = groupChoiceOptions([...options, FREE_INPUT], FREE_INPUT);
    expect(grouped?.groups.map((group) => group.title)).toEqual(titles);
    expect(grouped?.groups.flatMap((group) => group.options)).toEqual(options);
    expect(grouped?.placeholder).toBe(placeholder);
  });

  // 닫힌 선택지(유니버스·리밸런싱 방식)는 자유 입력이 없다 — 목록 정본에도 두지 않는다.
  it("닫힌 선택지 목록은 정본에 없어 평평하게 남는다", () => {
    expect(
      groupChoiceOptions(["종목 교체 리밸런싱", "비중 조정 리밸런싱 (균등 유지)"], FREE_INPUT),
    ).toBeNull();
  });

  it("유니버스처럼 정본에 없는 목록은 평평한 목록으로 남긴다", () => {
    expect(
      groupChoiceOptions(["코스피", "코스닥", "코스피200", "코스피·코스닥 전체", "ETF"], FREE_INPUT),
    ).toBeNull();
    expect(groupChoiceOptions(["1 ~ 100", FREE_INPUT], FREE_INPUT)).toBeNull();
  });

  it("한 칩만 겹치면 그 목록으로 보지 않는다(맞지 않는 문구를 끌어오지 않는다)", () => {
    expect(groupChoiceOptions(["손절 -10%", "일부 청산", FREE_INPUT], FREE_INPUT)).toBeNull();
  });

  it("어느 묶음에도 없는 칩은 잃지 않는다", () => {
    const grouped = groupChoiceOptions(
      ["RSI 30 이하에서 매수", "PER 10 이하", "삼성전자 관련주", FREE_INPUT],
      FREE_INPUT,
    );
    expect(grouped?.groups.map((group) => group.title)).toEqual(["매수 시점 신호", "종목 필터", ""]);
    expect(grouped?.groups.at(-1)?.options).toEqual(["삼성전자 관련주"]);
  });

  it("제목 없는 목록에 낯선 칩이 섞여도 한 칸에 원래 순서로 담는다", () => {
    const grouped = groupChoiceOptions(
      ["최대 5종목", "최대 10종목", "최대 3종목", FREE_INPUT],
      FREE_INPUT,
    );
    expect(grouped?.groups).toEqual([
      { title: "", options: ["최대 5종목", "최대 10종목", "최대 3종목"] },
    ]);
  });
});
