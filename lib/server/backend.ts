import { fetch as undiciFetch, Agent } from "undici";

const DEFAULT_BACKEND_URLS = [
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

// Node 내장 fetch(undici)의 기본 headersTimeout/bodyTimeout은 300초이고, 글로벌 fetch에
// 외부 undici Agent를 dispatcher로 넘겨도 내부 undici가 이를 무시해 300초 한도가 유지된다.
// 코치 콜드스타트(Modal 컨테이너 기동 + 모델 로드 + 첫 추론)는 worst-case ~520초까지 걸리는데,
// AbortSignal.timeout(560초)을 줘도 300초에 "fetch failed"로 끊겨 사용자는 응답을 못 받는다.
// 그래서 undici 자체 fetch를 같은 라이브러리의 Agent와 함께 써서(타임아웃 0=비활성) AbortSignal을
// 유일한 상한으로 삼아 timeoutMs 예산이 실제로 유지되게 한다.
let backendAgent: Agent | undefined;
function getBackendAgent(): Agent {
  if (!backendAgent) {
    backendAgent = new Agent({ headersTimeout: 0, bodyTimeout: 0 });
  }
  return backendAgent;
}

export function getBackendBaseUrls(): string[] {
  const envUrl = process.env.BACKEND_URL?.trim();
  const urls = envUrl ? [envUrl, ...DEFAULT_BACKEND_URLS] : DEFAULT_BACKEND_URLS;
  return Array.from(new Set(urls));
}

// 호출자의 signal(보통 라우트의 req.signal — 클라이언트가 연결을 끊으면 abort)과 timeoutMs
// 예산을 합친다. 예전엔 timeout signal이 호출자 signal을 덮어써서, 사용자가 '대화 종료'로
// 요청을 끊어도 백엔드 연결은 예산이 다할 때까지 살아 있었다(백엔드 LLM 작업이 계속됨).
// (AbortSignal.any 대신 수동 결합 — 런타임 Node 24엔 있지만 jsdom 테스트 환경엔 없다.)
function combineSignals(callerSignal: AbortSignal | null | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  if (!callerSignal) return timeout;
  const combined = new AbortController();
  const forward = (source: AbortSignal) => () => combined.abort(source.reason);
  if (callerSignal.aborted) combined.abort(callerSignal.reason);
  else callerSignal.addEventListener("abort", forward(callerSignal), { once: true });
  timeout.addEventListener("abort", forward(timeout), { once: true });
  return combined.signal;
}

export async function fetchBackend(
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const { timeoutMs, signal, ...requestInit } = init ?? {};
  const errors: string[] = [];

  for (const baseUrl of getBackendBaseUrls()) {
    // 호출자가 이미 끊었으면(클라이언트 연결 종료) 다음 후보 URL로 넘어가지 않는다.
    if (signal?.aborted) throw signal.reason ?? new Error("request aborted");
    try {
      const response = await undiciFetch(`${baseUrl}${path}`, {
        ...(requestInit as Record<string, unknown>),
        signal: combineSignals(signal, timeoutMs ?? 120_000),
        dispatcher: getBackendAgent(),
      });
      return response as unknown as Response;
    } catch (error: any) {
      errors.push(`${baseUrl}: ${error?.message ?? "fetch failed"}`);
    }
  }

  throw new Error(errors.join(" | "));
}
