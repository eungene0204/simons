import { parseSseBlocks } from "./sseEvents";

export interface WalkForwardProgressEvent {
  stage: "prepare" | "window" | string;
  window?: number;
  total?: number;
  is_period?: string;
  oos_period?: string;
  message?: string;
}

export type WalkForwardProgressHandler = (event: WalkForwardProgressEvent) => void;

// 워크포워드 SSE 스트림을 소비해 진행률 이벤트를 전달하고 최종 결과를 반환한다.
// 이벤트 형식: {type: "progress"|"result"|"error", ...} + 종료 시 "[DONE]".
export async function runWalkForwardStream(
  requestBody: unknown,
  options: { signal?: AbortSignal; onProgress?: WalkForwardProgressHandler } = {}
): Promise<any> {
  const res = await fetch("/api/backtest/walk-forward/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
    signal: options.signal,
  });

  if (!res.ok || !res.body) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail ?? error.message ?? "워크포워드 분석 실패");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: any = null;

  const handlePayload = (payload: string) => {
    if (payload === "[DONE]") return;
    let event: any;
    try {
      event = JSON.parse(payload);
    } catch {
      return;
    }
    if (event.type === "progress") {
      options.onProgress?.(event as WalkForwardProgressEvent);
    } else if (event.type === "result") {
      result = event.data;
    } else if (event.type === "error") {
      throw new Error(event.message ?? "워크포워드 분석 실패");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      const parsed = parseSseBlocks(buffer + decoder.decode(), true);
      for (const event of parsed.events) handlePayload(event.payload);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBlocks(buffer);
    buffer = parsed.remaining;
    for (const event of parsed.events) handlePayload(event.payload);
  }

  if (!result) {
    throw new Error("워크포워드 분석 결과를 받지 못했습니다.");
  }
  return result;
}
