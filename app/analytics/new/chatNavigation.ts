import { PENDING_STRATEGY_PROMPT_KEY } from "@/components/strategy/strategyTemplateSession";

export function shouldBeginStrategyChatNavigation(
  isChatPage: boolean,
  messageCount: number
) {
  return !isChatPage && messageCount === 0;
}

export function beginStrategyChatNavigation(
  prompt: string,
  navigate: (url: string) => void,
  storage: Storage = window.sessionStorage
) {
  storage.setItem(PENDING_STRATEGY_PROMPT_KEY, prompt);
  navigate("/analytics/chat");
}

type ChatInputVisibilityMessage = {
  role: string;
  content?: string;
  parsed?: unknown;
  stockAnalysis?: unknown;
  infoText?: string;
  error?: string;
  infoSuggestions?: string[];
};

// 채팅 입력창 노출 여부. 에러로 끝난 메시지도 '응답이 있는 메시지'로 쳐야 한다 — 그렇지
// 않으면 오류 발생 시 parsed/stockAnalysis/infoText가 하나도 없어 입력창이 영영 안 나타나고
// 사용자가 다음 메시지를 보낼 수도, 대화를 끝낼 수도 없는 상태로 갇힌다.
export function shouldShowChatInputBox(
  messages: ChatInputVisibilityMessage[],
  isIdle: boolean,
  builderFreeTextRequested: boolean
): boolean {
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === "assistant");
  const builderAwaitingChoice = (lastAssistantMessage?.infoSuggestions?.length ?? 0) > 0;
  const hasRespondedMessage = messages.some(
    (m) => m.parsed || m.stockAnalysis || m.infoText || m.error
  );
  return (isIdle || hasRespondedMessage) && (!builderAwaitingChoice || builderFreeTextRequested);
}

type PersistableChatMessage = {
  role: string;
  content?: string;
  parsed?: unknown;
  coachText?: string;
  stockAnalysis?: unknown;
  infoText?: string;
  error?: string;
  clarification?: string;
  isLoading?: boolean;
  stockLoading?: boolean;
  coachLoading?: boolean;
};

// 채팅 상태를 세션에 저장하기 전 메시지를 정리한다.
// - 로딩(분석/검증 중) 플래그는 복원해도 응답이 다시 오지 않아 영구 로딩으로 보이므로 끈다.
// - 콘텐츠가 없는 빈 자리표시자 메시지는 저장에서 제외한다.
export function selectPersistableChatMessages<T extends PersistableChatMessage>(
  messages: T[]
): T[] {
  return messages
    .map((m) => ({ ...m, isLoading: false, stockLoading: false, coachLoading: false }))
    .filter(
      (m) =>
        m.role === "user" ||
        Boolean(
          m.content ||
            m.parsed ||
            m.coachText ||
            m.stockAnalysis ||
            m.infoText ||
            m.error ||
            m.clarification
        )
    );
}
