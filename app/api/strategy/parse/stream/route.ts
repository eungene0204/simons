import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

type ParseStreamBody = {
  prompt?: string;
  backend?: string;
  model?: string;
  previous_parsed?: Record<string, unknown>;
  previous_coach_text?: string;
  // 직전 planner ask 컨텍스트 에코(칩 클릭의 결정론 귀속 — 백엔드 무상태 계약)
  pending_ask?: { topic?: string | null; question: string; chips: string[] } | null;
  // 답을 기다리는 되묻기 질문 에코 — 필드 없이 값만 온 답을 인터프리터가 귀속하는 근거
  pending_question?: string | null;
  // 이전 턴까지 사용자가 명시한 설정 필드 에코(provenance 누적 — 무상태 계약)
  previous_explicit_fields?: string[];
  // 값 변경 추적 메타데이터 에코(비권위 — 판정에 쓰지 않는다)
  previous_field_metadata?: Record<string, unknown> | null;
  // 영속 Artifact 상태 에코(비싼 도구 산출물의 근거·유효성)
  previous_artifacts?: Record<string, unknown> | null;
  // 직전 턴 파생 상태 에코(무효화·재유효화 전이 판정의 유일한 입력)
  previous_field_states?: Record<string, unknown> | null;
};

function sseEvent(data: object | string): string {
  const payload = typeof data === "string" ? data : JSON.stringify(data);
  return `data: ${payload}\n\n`;
}

function compactPrompt(prompt: string): string {
  return prompt.toLowerCase().replace(/\s+/g, "");
}

function previousUniverse(body: ParseStreamBody): string[] | null {
  const universe = body.previous_parsed?.universe;
  if (!Array.isArray(universe)) return null;
  const normalized = universe.filter((item): item is string => typeof item === "string" && item.length > 0);
  return normalized.length > 0 ? normalized : null;
}

function inferUniverse(prompt: string, body?: ParseStreamBody): string[] {
  const compact = compactPrompt(prompt);
  if (compact.includes("코스피200") || compact.includes("kospi200")) return ["KOSPI200"];
  if (
    compact.includes("전체시장") ||
    compact.includes("코스피+코스닥") ||
    compact.includes("kospi+kosdaq")
  ) {
    return ["KOSPI", "KOSDAQ"];
  }
  if (compact.includes("코스닥") || compact.includes("kosdaq")) return ["KOSDAQ"];
  if (compact.includes("코스피") || compact.includes("kospi")) return ["KOSPI"];
  const inherited = body ? previousUniverse(body) : null;
  if (inherited) return inherited;
  return ["KOSPI200"];
}

function inferMaxPositions(prompt: string): number | null {
  const match = compactPrompt(prompt).match(/(?:최대|상위)?(\d+)(?:개|종목)/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(100, parsed)) : null;
}

function inferRecognizedTerms(prompt: string): string[] {
  const compact = compactPrompt(prompt);
  const terms: Array<[string, string[]]> = [
    ["pbr", ["pbr"]],
    ["per", ["per"]],
    ["roe", ["roe", "gpa"]],
    ["ma_crossover", ["골든크로스", "데드크로스", "이동평균", "이평선"]],
    ["rsi", ["rsi"]],
    ["macd", ["macd"]],
    ["bollinger_bands", ["볼린저", "bollinger"]],
    ["breakout", ["신고가", "브레이크아웃", "breakout"]],
    ["stop_loss", ["손절", "손실", "하락"]],
    ["take_profit", ["익절", "수익"]],
    ["hold_period", ["보유", "리밸런싱"]],
  ];

  return terms
    .filter(([, keywords]) => keywords.some((keyword) => compact.includes(keyword)))
    .map(([term]) => term);
}

function buildSkeleton(body: ParseStreamBody) {
  const prompt = String(body.prompt ?? "");
  const recognizedTerms = inferRecognizedTerms(prompt);

  return {
    type: "skeleton",
    data: {
      description: prompt,
      universe: inferUniverse(prompt, body),
      max_positions: inferMaxPositions(prompt),
      recognized_terms: recognizedTerms,
      confidence: recognizedTerms.length > 0 ? "partial" : "low",
    },
  };
}

function streamHeaders() {
  return {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  };
}

export async function POST(req: NextRequest) {
  let body: ParseStreamBody;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();
      const send = (event: object | string) => {
        controller.enqueue(encoder.encode(sseEvent(event)));
      };

      send({ type: "accepted" });
      send(buildSkeleton(body));

      // 백엔드 parse-stream의 SSE 이벤트를 받아 클라이언트용 이벤트로 변환한다.
      // - stage: 그대로 전달(parsing→thinking 진행 표시)
      // - result: parsed_final + dsl_ready로 분해
      // - result_update: 후행 LLM 검증 교정 → parsed_updated 단일 이벤트로 전달
      // - error: detail 전달
      const handleEvent = (payload: string) => {
        if (payload === "[DONE]") return;
        let event: any;
        try {
          event = JSON.parse(payload);
        } catch {
          return;
        }
        if (event.type === "stage") {
          send({ type: "stage", stage: event.stage });
        } else if (event.type === "result") {
          const data = event.data ?? {};
          send({
            type: "parsed_final",
            parsed: data.parsed,
            clarification_question: data.clarification_question ?? null,
            clarification_suggestions: data.clarification_suggestions ?? null,
            // 우선순위 마커가 빠지면 프론트의 theme_universe 우선 게이트가 되묻기를
            // 인식하지 못해 explicit 설정 질문(시장)이 덮어쓴다 — 'bts 관련 종목'이
            // 업종 전체로 강등되던 실측 사고(2026-07-25, 프록시 화이트리스트 누락).
            clarification_priority: data.clarification_priority ?? null,
            // planner ask 컨텍스트 — 프론트가 다음 파스 요청의 pending_ask로 에코한다.
            // 화이트리스트 누락 시 칩 클릭 결정론 귀속이 조용히 죽는다(priority 마커
            // 누락 사고와 같은 함정 — 위 주석 참조).
            pending_ask: data.pending_ask ?? null,
            risk_overrides: data.risk_overrides ?? null,
            // 사용자가 실제로 말한 설정 필드(provenance). 프론트 되묻기 게이트·진행률이
            // 이 값만 보고 판정하므로, 화이트리스트에서 빠지면 모든 설정을 "미언급"으로
            // 보고 영원히 되묻는다(clarification_priority·pending_ask와 같은 함정).
            explicit_fields: data.explicit_fields ?? null,
            // 진행 골격 8칸의 상태 축(완료/미확인/해당 없음/확인 필요). 진행률 카드가
            // '해당 없음'을 '완료'로 위장하지 않기 위한 표시 전용 정보다 — 되묻기·실행
            // 게이트는 쓰지 않으므로 누락돼도 흐름은 그대로다(카드 표시만 예전으로 회귀).
            field_states: data.field_states ?? null,
            // 값 미정으로 컴파일에서 제외된 조건 [{role,label,source_text}] — 요약이
            // "이해했지만 값 대기"를 표시할 유일한 근거(parsed에는 없다). 누락되면
            // 이해한 조건이 빈 전략으로 보인다(2026-08-03 '당기순이익' 사고 — 백엔드는
            // 실어 보냈는데 이 화이트리스트에서 떨어져 실제 서비스에서 재발했다).
            pending_conditions: data.pending_conditions ?? null,
            // 이 턴이 바꾼 필드(§ 19) — 클라이언트가 변경 이력에 쌓아 되돌리기의 근거로
            // 쓴다. 누락되면 이력이 "무엇이 바뀌었는지 모르는" 상태가 돼 되돌리기가
            // 항상 되묻기로 강등된다.
            changed_fields: data.changed_fields ?? null,
            // 값 변경 추적 메타데이터(비권위) — 어느 턴에 무엇이 왜 바뀌었는지의 기록.
            // 판정에 쓰지 않으므로 누락돼도 동작은 그대로다(추적 정보만 끊긴다).
            field_metadata: data.field_metadata ?? null,
            // 영속 Artifact 상태 — 비싼 도구 산출물(테마 종목)의 근거와 유효성.
            // 재조회가 비싸 "아직 맞나"를 재실행으로 확인할 수 없어 기록으로 나른다.
            artifacts: data.artifacts ?? null,
            // 변경 영향 범위(§ 8·§ 30) — 이번 턴이 무엇을 쓸 수 없게/있게 만들었나.
            // 내부 추적용이며 사용자 문구를 만들지 않는다(안내는 검증기 담당).
            impact: data.impact ?? null,
            notices: data.notices ?? null,
          });
          send({
            type: "dsl_ready",
            backtest_request: data.backtest_request,
            symbol_count: data.symbol_count ?? data.backtest_request?.symbol_count ?? null,
          });
        } else if (event.type === "result_update") {
          // 룰 파스 결과를 먼저 보낸 뒤 도착한 검증 교정본. 클라이언트가 실행 전이면
          // 전략·백테스트 요청을 조용히 갱신한다(로딩 표시로 되돌아가지 않음).
          const data = event.data ?? {};
          send({
            type: "parsed_updated",
            parsed: data.parsed,
            backtest_request: data.backtest_request,
            symbol_count: data.symbol_count ?? null,
            risk_overrides: data.risk_overrides ?? null,
            notices: data.notices ?? null,
          });
        } else if (event.type === "error") {
          send({ type: "error", detail: event.detail ?? "파싱 실패" });
        }
      };

      const processBlocks = (blocks: string[]) => {
        for (const block of blocks) {
          if (!block.trim()) continue;
          const line = block.split(/\r?\n/).find((l) => l.startsWith("data: "));
          if (line) handleEvent(line.slice(6).trim());
        }
      };

      try {
        const res = await fetchBackend("/strategy/parse-stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          cache: "no-store",
          // 파스 한 턴은 LLM 3회로 약 800~1,000토큰을 **생성**한다 — 예산을 지배하는 건
          // 프롬프트 길이가 아니라 이 생성량이고, 그래서 소요 시간이 머신의 그 시각
          // 처리량에 정비례한다(실측 2026-08-07: 같은 요청이 처리량 11 tok/s에서 65초,
          // 4 tok/s에서 300초). 120초는 정상 처리량에서도 여유가 얇아 경합이 조금만
          // 끼면 파싱이 끝났는데도 프록시가 먼저 끊었다("aborted due to timeout").
          // 백엔드 per-call 상한(180초)과 후행 검증 상한(90초)의 합을 담는 값이다.
          timeoutMs: 240_000,
        });

        if (!res.ok || !res.body) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          send({ type: "error", detail: err.detail ?? res.statusText });
          send("[DONE]");
          controller.close();
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            buffer += decoder.decode();
            processBlocks(buffer.split(/\r?\n\r?\n/));
            buffer = "";
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\r?\n\r?\n/);
          buffer = blocks.pop() ?? "";
          processBlocks(blocks);
        }

        send("[DONE]");
        controller.close();
      } catch (error: any) {
        send({ type: "error", detail: `Strategy parse stream proxy error: ${error.message}` });
        send("[DONE]");
        controller.close();
      }
    },
  });

  return new NextResponse(stream, {
    status: 200,
    headers: streamHeaders(),
  });
}
