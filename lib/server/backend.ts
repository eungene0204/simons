import { fetch as undiciFetch, Agent } from "undici";
import {
  isRegion,
  REGION_COOKIE,
  REGION_HEADER,
  REGION_LANGUAGE,
} from "@/lib/geo/region";

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

// 요청 지역(미들웨어 헤더, API 라우트는 지역 쿠키 폴백)의 UI 언어를 백엔드에 X-UI-Language
// 헤더로 넘긴다 — 백엔드 LLM 자유 서술(되묻기 질문·리포트·일반 답변)의 언어 지시에 쓰인다.
// 라우트 핸들러 밖(요청 컨텍스트 없음)이면 생략.
function uiLanguageHeader(): Record<string, string> {
  try {
    // 정적 import를 피한다 — 이 모듈은 요청 컨텍스트 밖(스케줄러 등)에서도 쓰이므로 필요할 때만 읽는다.
    const { cookies, headers } = require("next/headers") as typeof import("next/headers");
    const headerValue = headers().get(REGION_HEADER);
    const region = isRegion(headerValue) ? headerValue : cookies().get(REGION_COOKIE)?.value;
    return isRegion(region) ? { "X-UI-Language": REGION_LANGUAGE[region] } : {};
  } catch {
    return {};
  }
}

// 백엔드의 관리자·내부·운영 변경 엔드포인트는 내부 토큰을 요구한다(backend/internal_auth.py,
// NFR-SEC-012). 백엔드는 내부망에만 있으므로 모든 요청에 실어도 노출되지 않는다.
export function internalTokenHeader(): Record<string, string> {
  const token = process.env.INTERNAL_API_TOKEN?.trim();
  return token ? { "X-Internal-Token": token } : {};
}

/**
 * 백엔드 URL 경로에 끼워 넣을 값 하나를 조각 하나로 만든다. 거부하면 null.
 *
 * 라우트 파라미터(`[symbol]` 등)는 Next가 디코드해 넘긴다 — '..%2F..%2Fadmin%3F'가
 * '../../admin?'이 되어, 그대로 끼우면 URL 정규화로 백엔드의 다른 경로(관리자 조회 등)에
 * 닿았다(2026-10-11 실측: 비로그인 요청이 /ontology/graph 응답을 받음). 백엔드는 외부에
 * 노출되지 않는다는 전제로 인증 없이 동작하므로, Next에서 경로 조각을 반드시 가둔다.
 * '/'·'?'·'#'은 인코딩하고, 정규화로 상위로 올라가는 '.'·'..'와 빈 값은 거부한다.
 */
export function backendPathSegment(value: unknown): string | null {
  const text = value == null ? "" : String(value);
  if (text === "" || text === "." || text === "..") return null;
  return encodeURIComponent(text);
}

// fetchBackend 경로의 '.'·'..' 조각 — 경로를 조립한 쪽이 조각을 가두지 않았을 때의 마지막 그물.
function hasDotSegment(path: string): boolean {
  const pathname = path.split(/[?#]/)[0];
  // URL 해석기는 http 주소의 '\\'를 '/'로 취급한다 — '..\\..\\admin'도 상위로 올라간다.
  if (pathname.includes("\\")) return true;
  return pathname.split("/").some((segment) => {
    const decoded = (() => {
      try {
        return decodeURIComponent(segment);
      } catch {
        return segment;
      }
    })();
    return decoded === "." || decoded === "..";
  });
}

export async function fetchBackend(
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  if (hasDotSegment(path)) {
    throw new Error(`unsafe backend path: ${path.slice(0, 80)}`);
  }
  const { timeoutMs, signal, ...requestInit } = init ?? {};
  const errors: string[] = [];
  const callerHeaders =
    requestInit.headers instanceof Headers
      ? Object.fromEntries(requestInit.headers.entries())
      : Array.isArray(requestInit.headers)
        ? Object.fromEntries(requestInit.headers)
        : ((requestInit.headers as Record<string, string> | undefined) ?? {});
  requestInit.headers = { ...uiLanguageHeader(), ...internalTokenHeader(), ...callerHeaders };

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
