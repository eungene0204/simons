export type ParsedSseEvent = {
  payload: string;
};

export function parseSseBlocks(buffer: string, flush = false): {
  events: ParsedSseEvent[];
  remaining: string;
} {
  const parts = buffer.split(/\r?\n\r?\n/);
  const remaining = flush ? "" : parts.pop() ?? "";
  const completeParts = flush ? parts : parts;

  return {
    events: completeParts
      .map((part) => {
        const data = part
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6).trim())
          .join("\n");
        return data ? { payload: data } : null;
      })
      .filter((event): event is ParsedSseEvent => event !== null),
    remaining,
  };
}
