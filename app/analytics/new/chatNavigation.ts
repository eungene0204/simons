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
  // 별도 라우트(/analytics/chat)로 push하면 무거운 채팅 컴포넌트가 통째로 remount되고
  // authState가 loading으로 초기화돼 /api/user 왕복이 끝날 때까지 첫 전략 전송이 지연된다.
  // 같은 라우트의 쿼리(?chat=1)로 soft navigation하면 컴포넌트가 유지돼 즉시 전환된다.
  navigate("/analytics?chat=1");
}

type ChatInputVisibilityMessage = {
  role: string;
  content?: string;
  parsed?: unknown;
  infoText?: string;
  error?: string;
  infoSuggestions?: string[];
};

// 채팅 입력창 노출 여부. 에러로 끝난 메시지도 '응답이 있는 메시지'로 쳐야 한다 — 그렇지
// 않으면 오류 발생 시 parsed/infoText가 하나도 없어 입력창이 영영 안 나타나고
// 사용자가 다음 메시지를 보낼 수도, 대화를 끝낼 수도 없는 상태로 갇힌다.
export function shouldShowChatInputBox(
  messages: ChatInputVisibilityMessage[],
  isIdle: boolean,
  builderFreeTextRequested: boolean
): boolean {
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === "assistant");
  const builderAwaitingChoice = (lastAssistantMessage?.infoSuggestions?.length ?? 0) > 0;
  const hasRespondedMessage = messages.some(
    (m) => m.parsed || m.infoText || m.error
  );
  return (isIdle || hasRespondedMessage) && (!builderAwaitingChoice || builderFreeTextRequested);
}

type PersistableChatMessage = {
  role: string;
  content?: string;
  parsed?: unknown;
  coachText?: string;
  infoText?: string;
  error?: string;
  clarification?: string;
  isLoading?: boolean;
  coachLoading?: boolean;
};

// 채팅 상태를 세션에 저장하기 전 메시지를 정리한다.
// - 로딩(분석/검증 중) 플래그는 복원해도 응답이 다시 오지 않아 영구 로딩으로 보이므로 끈다.
// - 콘텐츠가 없는 빈 자리표시자 메시지는 저장에서 제외한다.
export function selectPersistableChatMessages<T extends PersistableChatMessage>(
  messages: T[]
): T[] {
  return messages
    .map((m) => ({ ...m, isLoading: false, coachLoading: false }))
    .filter(
      (m) =>
        m.role === "user" ||
        Boolean(
          m.content ||
            m.parsed ||
            m.coachText ||
            m.infoText ||
            m.error ||
            m.clarification
        )
    );
}
