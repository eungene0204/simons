/** 되묻기 선택 목록의 표시 정본 — 자유 입력창 자리표시자·칩 묶음 소제목·한 줄 안내.
 *
 * 매수 조건 질문은 "언제 사는가"(시점 신호)·"누구를 줄 세워 담는가"(랭킹)·"어떤 종목만
 * 대상으로 하는가"(필터)가 한 목록에 평평하게 섞여 있어, 칩만 보고는 셋의 차이를 알 수
 * 없었다(2026-09-04). 그 박스의 설계 의도는 넷이다:
 *   ① 주 채널인 자유 서술을 칩 **위**에 미리 연다('직접 입력'이 마지막 칩으로 묻혀 있었다)
 *   ② 성격이 다른 칩은 소제목으로 가른다
 *   ③ 칩 하나로 못 고르는 답의 진입로를 한 줄 안내로 알린다
 *   ④ 칩 문구·값·순번은 그대로 둔다(칩=값 결속 계약, engine/strategy_slots.py ↔
 *      deterministicConditionFlow.ts) — 묶음은 **표시만** 바꾼다
 *
 * [2026-09-06 사용자 지시] 같은 의도를 유니버스를 뺀 나머지 슬롯 박스에도 적용한다.
 * 다만 ②는 성격이 실제로 갈리는 목록에만 온다 — 손절 -5/-10/-15%처럼 한 축의 값만 있는
 * 목록에 소제목을 붙이면 정보가 아니라 소음이다. 그런 목록은 ①③만 받고 평평하게 그린다.
 * 유니버스·리밸런싱 방식은 제외한다 — 닫힌 선택지라 자유 입력 자체가 없다(제시한 두세
 * 선택지가 답의 전부다, backtestReadiness의 isClosedChoiceSlot).
 *
 * 키는 choiceOptionHelp와 같이 **칩 문자열 그대로**다. 칩 문구가 바뀌면 그 칩은 목록
 * 정본에서 빠져 평평한 목록으로 돌아간다(어긋난 묶음이 조용히 남는 것보다 낫다).
 */

export type ChoiceOptionGroup = { title: string; options: string[] };

export type GroupedChoiceOptions = {
  groups: ChoiceOptionGroup[];
  /** 자유 입력창의 자리표시자 — 이 목록이 묻는 것에 맞춘다. */
  placeholder: string;
  /** 목록 아래 한 줄 안내 — 칩 하나로 못 고르는 답의 진입로를 알린다. 빈 문자열이면 없다. */
  note: string;
};

type ListSpec = {
  groups: ReadonlyArray<{ title: string; members: ReadonlyArray<string> }>;
  placeholder: string;
  note?: string;
};

// 규제 안전 원칙: 소제목·안내는 그 묶음이 **무엇인지**만 말한다. 어느 쪽이 낫다는 판단은 없다.
// 안내는 엔진이 실제로 받는 답만 알린다 — 리밸런싱 주기는 capability_registry의 지원 목록
// (daily·weekly·monthly·bimonthly·quarterly·yearly), 백테스트 기간은 명시 연도 지정.
const LIST_SPECS: ReadonlyArray<ListSpec> = [
  // 매수 조건(engine/strategy_slots.py ENTRY)
  {
    groups: [
      {
        title: "매수 시점 신호",
        members: [
          "골든크로스(5일/20일) 발생 시 매수",
          "RSI 30 이하에서 매수",
          "MACD 골든크로스 매수",
          "볼린저밴드 하단 터치 시 매수",
          "20일 고점 돌파 시 매수",
          "거래량 급증 시 매수",
        ],
      },
      { title: "순위로 담기", members: ["최근 3개월 수익률 상위 매수"] },
      { title: "종목 필터", members: ["PER 10 이하", "ROE 15% 이상", "PBR 1 이하"] },
    ],
    placeholder: "원하는 매수 조건을 직접 적어 주세요",
    note: "종목 필터와 매수 시점 신호는 함께 쓸 수 있어요. 함께 쓰려면 위 입력창에 한 번에 적어 주세요.",
  },
  // 매도 조건(EXIT) — 신호로 파는 것과 정해진 기간이 지나 파는 것은 성격이 다르다.
  {
    groups: [
      {
        title: "매도 시점 신호",
        members: [
          "데드크로스(5일/20일) 발생 시 매도",
          "RSI 70 이상에서 매도",
          "MACD 데드크로스 매도",
          "볼린저밴드 상단 터치 시 매도",
          "20일 저점 이탈 시 매도",
        ],
      },
      { title: "기간으로 청산", members: ["20일 보유 후 청산"] },
    ],
    placeholder: "원하는 매도 조건을 직접 적어 주세요",
    note: "매도 조건은 여러 개를 함께 쓸 수 있어요. 함께 쓰려면 위 입력창에 한 번에 적어 주세요.",
  },
  // 최대 보유 — 한 축의 값이라 묶지 않는다(기본·분위 그룹·랭킹 세 변형).
  {
    groups: [{ title: "", members: ["최대 5종목", "최대 10종목", "최대 20종목"] }],
    placeholder: "원하는 종목 수를 직접 적어 주세요",
    note: "칩에 없는 종목 수도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [{ title: "", members: ["그룹당 10종목", "그룹당 20종목", "그룹당 30종목"] }],
    placeholder: "그룹당 담을 종목 수를 직접 적어 주세요",
    note: "칩에 없는 종목 수도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [{ title: "", members: ["상위 5종목", "상위 10종목", "상위 20종목"] }],
    placeholder: "보유할 상위 종목 수를 직접 적어 주세요",
    note: "칩에 없는 종목 수도 위 입력창에 적을 수 있어요.",
  },
  // 리밸런싱 — 주기를 고르는 것과 하지 않기로 하는 것은 성격이 다르다.
  {
    groups: [
      {
        title: "정해진 주기마다",
        members: ["매주 리밸런싱", "매월 리밸런싱", "분기마다 리밸런싱"],
      },
      { title: "사용 안 함", members: ["리밸런싱 안 함"] },
    ],
    placeholder: "원하는 리밸런싱 주기를 직접 적어 주세요",
    note: "칩에 없는 주기(매일·2개월마다·매년)도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [
      { title: "손절 폭", members: ["손절 -5%", "손절 -10%", "손절 -15%"] },
      { title: "사용 안 함", members: ["손절 안 함"] },
    ],
    placeholder: "원하는 손절 기준을 직접 적어 주세요",
    note: "칩에 없는 값(예: -7% 손절)도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [
      { title: "익절 폭", members: ["익절 10%", "익절 20%", "익절 30%"] },
      { title: "사용 안 함", members: ["익절 안 함"] },
    ],
    placeholder: "원하는 익절 기준을 직접 적어 주세요",
    note: "칩에 없는 값(예: 15% 익절)도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [
      {
        title: "최근 기간",
        members: ["최근 1년 데이터", "최근 3년 데이터", "최근 5년 데이터"],
      },
      { title: "전체 기간", members: ["사용 가능한 전체 데이터"] },
    ],
    placeholder: "원하는 백테스트 기간을 직접 적어 주세요",
    note: "연도를 직접 지정할 수도 있어요(예: 2020년부터 2023년까지) — 위 입력창에 적어 주세요.",
  },
  // 초기 자본 — 한 축의 값. 미국 전략은 칩이 달러라 목록이 따로다(달러 칩=US 정본).
  {
    groups: [{ title: "", members: ["500만원", "1,000만원", "3,000만원", "5,000만원"] }],
    placeholder: "원하는 초기 자금을 직접 적어 주세요",
    note: "칩에 없는 금액도 위 입력창에 적을 수 있어요.",
  },
  {
    groups: [{ title: "", members: ["$10,000", "$30,000", "$50,000", "$100,000"] }],
    placeholder: "원하는 초기 자금을 직접 적어 주세요",
    note: "칩에 없는 금액도 위 입력창에 적을 수 있어요.",
  },
];

/** 목록 정본을 알아보는 최소 일치 칩 수. 한 개만 겹쳐도 알아본 것으로 치면, 다른 질문에
 *  우연히 섞여 나온 칩 하나가 그 질문에 맞지 않는 자리표시자·안내를 끌어온다. */
const MIN_MATCHED_MEMBERS = 2;

/** 목록을 정본에 맞춰 본다. 알아본 목록이면 자유 입력창 문구·묶음·안내를 돌려주고,
 *  아니면 null(호출자는 평평한 목록을 그린다).
 *
 *  묶음은 **둘 이상** 드러날 때만 소제목을 붙인다 — 소제목 하나는 정보가 아니라 소음이다.
 *  어느 묶음에도 없는 칩(자유 입력 칩 제외)은 제목 없는 꼬리 묶음으로 남겨 잃지 않는다. */
export function groupChoiceOptions(
  options: readonly string[],
  freeInputChip: string,
): GroupedChoiceOptions | null {
  for (const spec of LIST_SPECS) {
    const groups = spec.groups
      .map((group) => ({
        title: group.title,
        options: options.filter((option) => group.members.includes(option)),
      }))
      .filter((group) => group.options.length > 0);
    const matched = groups.reduce((count, group) => count + group.options.length, 0);
    if (matched < MIN_MATCHED_MEMBERS) continue;

    const grouped = new Set(groups.flatMap((group) => group.options));
    const rest = options.filter((option) => option !== freeInputChip && !grouped.has(option));
    // 소제목이 없는 목록에 꼬리 묶음을 따로 세우면 제목 없는 칸이 둘로 갈린다 — 한 칸에 담고
    // 원래 순서를 유지한다(순번 = 목록 순서).
    if (rest.length > 0 && groups.length === 1 && groups[0].title === "") {
      groups[0] = { title: "", options: options.filter((option) => option !== freeInputChip) };
    } else if (rest.length > 0) {
      groups.push({ title: "", options: rest });
    }
    // 소제목 하나는 정보가 아니라 소음이다 — 묶음이 하나면 제목을 떼고 평평하게 그린다.
    const titled = groups.length > 1 ? groups : [{ title: "", options: groups[0].options }];
    return { groups: titled, placeholder: spec.placeholder, note: spec.note ?? "" };
  }
  return null;
}
