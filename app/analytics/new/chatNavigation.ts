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
