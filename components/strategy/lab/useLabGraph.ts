"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { regionRequestHeaders } from "@/lib/geo/useRegion";
import type { ParsedSummary } from "@/lib/strategy-summary";
import { fromDraft } from "@/lib/strategy-graph/snapshot";
import { buildStrategyGraph } from "@/lib/strategy-graph/transform";
import type { StrategyGraph, StrategyGraphInput } from "@/lib/strategy-graph/types";
import { useGraphMeta } from "@/lib/strategy-graph/useGraphMeta";

// 캔버스 입력 규칙(그래프 입력은 진입점의 동결 스냅샷만 — docs/development/strategy-ontology-graph.md):
//  · 마지막 확정 스냅샷(확정 응답의 parsed+요청)이 지금 전략과 같으면 그 스냅샷을 그린다.
//  · 확정 뒤 전략이 바뀌었거나 아직 확정 전이면, 지금 parsed를 기존 결정론 컴파일
//    (/api/strategy/compile, LLM 없음)에 보내 얻은 parsed+요청 한 쌍(초안)을 그린다. 칩 답변 턴은
//    parsed만 갱신되고 요청은 낡을 수 있어 둘을 섞지 않는다.
export function loadDraftGraph(parsed: ParsedSummary, explicitFields: readonly string[]): Promise<StrategyGraphInput> {
  return fetch("/api/strategy/compile", {
    method: "POST",
    // The marker header only tells draft previews apart from the real confirm call (tests, logs).
    headers: { "Content-Type": "application/json", "X-Graph-Draft": "1", ...regionRequestHeaders() },
    body: JSON.stringify({ parsed }),
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      return fromDraft({ sourceRef: "draft:turn", parsed: data.parsed, request: data.backtest_request, notices: data.notices, explicitFields });
    })
    .then((input) => {
      if (input.origin === "none") throw new Error("empty");
      return input;
    });
}

export type LabGraphState = {
  graph: StrategyGraph | null;
  loading: boolean;
  /** 지표 메타데이터를 못 받았다 — 구조만 그리고 retryMeta()로 그 요청만 다시 한다. */
  metaError: boolean;
  retryMeta: () => void;
  /** 그래프를 그린 스냅샷(확정 또는 초안) — 노드 경로(sourceRef)가 가리키는 엔진 요청을 찾을 때 쓴다. */
  input: StrategyGraphInput | null;
};

export function useLabGraph(
  parsed: ParsedSummary | null,
  explicitFields: readonly string[],
  confirmed: StrategyGraphInput | null,
): LabGraphState {
  const meta = useGraphMeta();
  const [draft, setDraft] = useState<StrategyGraphInput | null>(null);
  const [loading, setLoading] = useState(false);
  const seqRef = useRef(0);
  const useConfirmed =
    !!confirmed && confirmed.origin === "confirmed" && !!parsed && JSON.stringify(confirmed.parsed) === JSON.stringify(parsed);
  const key = parsed && !useConfirmed ? JSON.stringify([parsed, explicitFields]) : "";

  useEffect(() => {
    const seq = ++seqRef.current;
    if (!key || !parsed) {
      setDraft(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    loadDraftGraph(parsed, explicitFields)
      .then((next) => {
        if (seq === seqRef.current) setDraft(next);
      })
      .catch(() => {
        // 컴파일되지 않는 초안은 그릴 구조가 없다 — 낡은 그래프를 남기지 않고 대화 요약에 맡긴다.
        if (seq === seqRef.current) setDraft(null);
      })
      .finally(() => {
        if (seq === seqRef.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key is the serialized parsed
  }, [key]);

  const input = useConfirmed ? confirmed : draft;
  const graph = useMemo(() => (input ? buildStrategyGraph(input, meta.meta) : null), [input, meta.meta]);
  return { graph, loading, metaError: meta.status === "error", retryMeta: meta.retry, input };
}
