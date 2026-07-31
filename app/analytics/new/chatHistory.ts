// intent 분류·일반 답변 API에 넘길 대화 맥락. "다른 예는 없어?" 같은 후속 질문은
// 문장만 보면 투자 신호가 없어 OFF_TOPIC으로 오판되므로, 최근 턴을 함께 보내
// 백엔드 LLM이 직전 주제의 연속으로 판단하게 한다.

export type ClassifierHistoryTurn = {
  role: "user" | "assistant";
  text: string;
};

type HistorySourceMessage = {
  role: string;
  content?: string;
  infoText?: string;
  coachText?: string;
  clarification?: string;
  isLoading?: boolean;
};

const MAX_TURNS = 6;
// 서버가 240자로 다시 자르므로 전송량만 가볍게 제한한다.
const MAX_TEXT_LENGTH = 500;

// 화면 메시지에서 맥락으로 쓸 텍스트를 고른다. 로딩 자리표시자·빈 메시지는 제외한다.
//
// assistant 메시지는 안내문(infoText)과 되묻기(clarification)를 **함께** 실을 수 있다
// (부가 발화에 답하면서 열린 질문을 다시 세우는 턴 — FR-SA-015). 예전처럼 앞의 것만
// 고르면 **우리가 방금 던진 질문이 맥락에서 사라져**, 그 답("아니야")이 문맥 없는 짧은
// 발화로 보여 인사·잡담으로 오분류된다(2026-07-31 실측). 있는 것을 모두 싣는다.
export function selectClassifierHistory(
  messages: HistorySourceMessage[],
  maxTurns: number = MAX_TURNS
): ClassifierHistoryTurn[] {
  const turns: ClassifierHistoryTurn[] = [];
  for (const m of messages) {
    if (m.isLoading) continue;
    const text =
      m.role === "user"
        ? m.content
        : [m.infoText, m.coachText, m.clarification].filter(Boolean).join("\n");
    if (!text?.trim()) continue;
    turns.push({
      role: m.role === "user" ? "user" : "assistant",
      text: text.slice(0, MAX_TEXT_LENGTH),
    });
  }
  return turns.slice(-maxTurns);
}
