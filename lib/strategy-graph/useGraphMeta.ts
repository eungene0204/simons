"use client";

import { useCallback, useEffect, useState } from "react";
import { loadGraphMeta } from "./meta";
import type { GraphMeta } from "./types";

export type GraphMetaState =
  | { status: "loading"; meta: null }
  | { status: "ready"; meta: GraphMeta }
  | { status: "error"; meta: null };

/** Loads the public indicator metadata. retry() re-requests only that endpoint. */
export function useGraphMeta(): GraphMetaState & { retry: () => void } {
  const [state, setState] = useState<GraphMetaState>({ status: "loading", meta: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    loadGraphMeta()
      .then((meta) => {
        if (!cancelled) setState({ status: "ready", meta });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", meta: null });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading", meta: null });
    setAttempt((n) => n + 1);
  }, []);

  return { ...state, retry };
}
