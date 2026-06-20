export function normalizeCoachMessage(value: unknown, fallback: string): string {
  if (typeof value !== "string") {
    return fallback;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }

  const codeBlockMatch = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/);
  const candidate = codeBlockMatch ? codeBlockMatch[1].trim() : trimmed;

  if (candidate.startsWith("{") && candidate.endsWith("}")) {
    try {
      const parsed = JSON.parse(candidate);
      if (typeof parsed?.is_valid === "boolean" && Array.isArray(parsed?.issues)) {
        const messages = parsed.issues
          .map((issue: unknown) => {
            if (!issue || typeof issue !== "object") return null;
            const message = (issue as { message?: unknown }).message;
            return typeof message === "string" && message.trim() ? message.trim() : null;
          })
          .filter((message: string | null): message is string => message !== null);

        if (messages.length > 0) {
          return messages.map((message: string) => `• ${message}`).join("\n");
        }

        return parsed.is_valid
          ? "전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다."
          : fallback;
      }
      if (typeof parsed?.message === "string" && parsed.message.trim()) {
        return parsed.message.trim();
      }
    } catch {
      return trimmed;
    }
  }

  return trimmed;
}
