/** 선택 칩 묶음의 정본 — 성격이 다른 칩이 한 목록에 섞일 때 소제목으로 갈라 보여준다.
 *
 * 매수 조건 질문은 "언제 사는가"(시점 신호)·"누구를 줄 세워 담는가"(랭킹)·"어떤 종목만
 * 대상으로 하는가"(필터)가 한 목록에 평평하게 섞여 있어, 칩만 보고는 셋의 차이를 알 수
 * 없었다(2026-09-04). 묶음은 **표시만** 바꾼다 — 칩 문구·값·순번은 그대로라 칩=값 결속
 * 계약(engine/strategy_slots.py ↔ deterministicConditionFlow.ts)을 건드리지 않는다.
 *
 * 키는 choiceOptionHelp와 같이 **칩 문자열 그대로**다. 칩 문구가 바뀌면 그 칩은 묶음에서
 * 빠져 평평한 목록으로 돌아간다(어긋난 묶음이 조용히 남는 것보다 낫다).
 *
 * 묶인 목록은 자유 입력창을 칩 **위**에 연 채로 둔다 — 이 제품의 주 채널은 자유 서술이고
 * 칩은 그 예시인데, '직접 입력'이 열 번째 칩으로 목록 끝에 묻혀 있었다. 필터와 신호를
 * 함께 쓰는 조합은 칩 하나로는 못 고르므로 입력창이 앞에 있어야 한다.
 */

export type ChoiceOptionGroup = { title: string; options: string[] };

export type GroupedChoiceOptions = {
  groups: ChoiceOptionGroup[];
  /** 자유 입력창의 자리표시자 — 이 목록이 묻는 것에 맞춘다. */
  placeholder: string;
  /** 목록 아래 한 줄 안내 — 칩 하나로 못 고르는 조합의 진입로를 알린다. */
  note: string;
};

type GroupSet = {
  groups: ReadonlyArray<{ title: string; members: ReadonlyArray<string> }>;
  placeholder: string;
  note: string;
};

// 규제 안전 원칙: 소제목·안내는 그 묶음이 **무엇인지**만 말한다. 어느 쪽이 낫다는 판단은 없다.
const ENTRY_GROUP_SET: GroupSet = {
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
    {
      title: "순위로 담기",
      members: ["최근 3개월 수익률 상위 매수"],
    },
    {
      title: "종목 필터",
      members: ["PER 10 이하", "ROE 15% 이상", "PBR 1 이하"],
    },
  ],
  placeholder: "원하는 매수 조건을 직접 적어 주세요",
  note: "종목 필터와 매수 시점 신호는 함께 쓸 수 있어요. 함께 쓰려면 위 입력창에 한 번에 적어 주세요.",
};

const GROUP_SETS: ReadonlyArray<GroupSet> = [ENTRY_GROUP_SET];

/** 목록을 묶음으로 나눈다. 묶음이 **둘 이상** 드러날 때만 묶는다 — 소제목 하나는 정보가
 *  아니라 소음이다. 어느 묶음에도 없는 칩(자유 입력 칩 제외)은 제목 없는 꼬리 묶음으로 남겨
 *  잃지 않는다. 묶을 수 없으면 null — 호출자는 평평한 목록을 그린다. */
export function groupChoiceOptions(
  options: readonly string[],
  freeInputChip: string,
): GroupedChoiceOptions | null {
  for (const set of GROUP_SETS) {
    const groups = set.groups
      .map((group) => ({
        title: group.title,
        options: options.filter((option) => group.members.includes(option)),
      }))
      .filter((group) => group.options.length > 0);
    if (groups.length < 2) continue;

    const grouped = new Set(groups.flatMap((group) => group.options));
    const rest = options.filter((option) => option !== freeInputChip && !grouped.has(option));
    if (rest.length > 0) groups.push({ title: "", options: rest });
    return { groups, placeholder: set.placeholder, note: set.note };
  }
  return null;
}
