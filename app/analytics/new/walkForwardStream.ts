import { parseSseBlocks } from "./sseEvents";
import { t } from "@/lib/i18n";

export interface WalkForwardProgressEvent {
  stage: "prepare" | "window" | string;
  window?: number;
  total?: number;
  is_period?: string;
  oos_period?: string;
  message?: string;
  // 창 내부 최적화 진행률 (시도 완료 수 / 전체 시도 수)
  trial?: number;
  trial_total?: number;
  // 최근 백테스트 단계별 소요 시간 (초)
  timing?: WalkForwardTiming;
  // 창 단위 병렬 실행일 때만 붙는 합산 진행률 (백엔드 WALK_FORWARD_WORKERS ≥ 2)
  windows_done?: number;   // 완료된 창 수
  trials_done?: number;    // 전 창 합산 완료 시도 수
  workers?: number;        // 동시 실행 워커 수
  active_windows?: number[]; // 지금 실행 중인 창 번호
}

export interface WalkForwardTiming {
  phase1: number;
  simulator: number;
  format: number;
  total: number;
  symbols: number;
}

export type WalkForwardProgressHandler = (event: WalkForwardProgressEvent) => void;

// 워크포워드 SSE 스트림을 소비해 진행률 이벤트를 전달하고 최종 결과를 반환한다.
// 이벤트 형식: {type: "progress"|"result"|"error", ...} + 종료 시 "[DONE]".
// fetch/스트림 도중 연결이 끊기면 브라우저는 "network error"/"Failed to fetch" 같은
// 원문 TypeError를 던진다. 사용자가 이해할 수 있는 안내로 바꿔준다.
// (사용자 취소 AbortError는 그대로 통과시켜 호출부가 취소로 처리하게 한다.)
const NETWORK_ERROR_MESSAGE =
  "서버와 연결이 끊겼습니다. 분석이 오래 걸리거나 백엔드 연결에 문제가 있을 수 있습니다. 잠시 후 다시 시도해 주세요.";

function isAbortError(error: unknown): boolean {
  // 취소는 DOMException("AbortError")로 오는데 런타임에 따라 Error를 상속하지
  // 않을 수 있으므로 name으로 판별한다.
  return typeof error === "object" && error !== null && (error as { name?: string }).name === "AbortError";
}

function isNetworkError(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof Error && /network error|failed to fetch|load failed|terminated/i.test(error.message))
  );
}

// FastAPI 에러 body의 detail/message를 사람이 읽는 문자열로 바꾼다.
// pydantic 검증 실패(422)의 detail은 객체 배열이라 그대로 Error에 넣으면
// "[object Object]"로 표시된다 — loc/msg를 뽑아 읽을 수 있게 만든다.
export function formatApiErrorDetail(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value == null) return null;
  if (Array.isArray(value)) {
    const lines = value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const { loc, msg } = item as { loc?: unknown[]; msg?: unknown };
          const path = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
          if (typeof msg === "string") return path ? `${path}: ${msg}` : msg;
        }
        return JSON.stringify(item);
      })
      .filter(Boolean);
    return lines.length > 0 ? lines.join(" / ") : null;
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export async function runWalkForwardStream(
  requestBody: unknown,
  options: { signal?: AbortSignal; onProgress?: WalkForwardProgressHandler } = {}
): Promise<any> {
  let res: Response;
  try {
    res = await fetch("/api/backtest/walk-forward/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (isNetworkError(error)) throw new Error(NETWORK_ERROR_MESSAGE);
    throw error;
  }

  if (!res.ok || !res.body) {
    const error = await res.json().catch(() => ({}));
    throw new Error(
      formatApiErrorDetail(error.detail) ?? formatApiErrorDetail(error.message) ?? t("워크포워드 분석 실패")
    );
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
      throw new Error(formatApiErrorDetail(event.message) ?? t("워크포워드 분석 실패"));
    }
  };

  try {
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
  } catch (error) {
    if (isAbortError(error)) throw error;
    // handlePayload가 던진 워크포워드 오류(한국어 메시지)는 그대로 노출한다.
    if (isNetworkError(error)) throw new Error(NETWORK_ERROR_MESSAGE);
    throw error;
  }

  if (!result) {
    throw new Error(t("워크포워드 분석 결과를 받지 못했습니다."));
  }
  return result;
}
