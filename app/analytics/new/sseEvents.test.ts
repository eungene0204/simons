import { describe, expect, it } from "vitest";
import { parseSseBlocks } from "./sseEvents";

describe("parseSseBlocks", () => {
  it("keeps incomplete trailing data until the next chunk", () => {
    const first = parseSseBlocks('data: {"type":"status","message":"분석 완료!"}\n\n' + 'data: {"type":"result"');

    expect(first.events).toEqual([
      { payload: '{"type":"status","message":"분석 완료!"}' },
    ]);
    expect(first.remaining).toBe('data: {"type":"result"');

    const second = parseSseBlocks(first.remaining + ',"data":{"totalReturn":7.7}}\n\n');

    expect(second.events).toEqual([
      { payload: '{"type":"result","data":{"totalReturn":7.7}}' },
    ]);
    expect(second.remaining).toBe("");
  });

  it("flushes a final result even without a trailing blank line", () => {
    const parsed = parseSseBlocks('data: {"type":"result","data":{"totalReturn":7.7}}', true);

    expect(parsed.events).toEqual([
      { payload: '{"type":"result","data":{"totalReturn":7.7}}' },
    ]);
    expect(parsed.remaining).toBe("");
  });

  it("parses result and done when both remain in the final buffer", () => {
    const parsed = parseSseBlocks(
      'data: {"type":"result","data":{"totalReturn":7.7}}\n\ndata: [DONE]',
      true,
    );

    expect(parsed.events).toEqual([
      { payload: '{"type":"result","data":{"totalReturn":7.7}}' },
      { payload: "[DONE]" },
    ]);
  });
});
