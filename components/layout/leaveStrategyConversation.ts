import {
  PENDING_STRATEGY_PROMPT_KEY,
  STRATEGY_CHAT_STATE_KEY,
} from "@/components/strategy/strategyTemplateSession";

export function leaveStrategyConversation(
  href: string,
  navigate: (destination: string) => void = (destination) =>
    window.location.replace(destination)
) {
  try {
    sessionStorage.removeItem(PENDING_STRATEGY_PROMPT_KEY);
    sessionStorage.removeItem(STRATEGY_CHAT_STATE_KEY);
  } catch {
    // Navigation still ends the current conversation when storage is unavailable.
  }

  navigate(href);
}
