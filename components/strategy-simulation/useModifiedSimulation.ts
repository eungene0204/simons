"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@/lib/i18n";

// 방문자 파라미터 수정 → 600ms 뒤 실제 재백테스트. 마지막 입력만 유효하고(앞선 요청은 취소·무시),
// 원본 결과는 읽기만 한다.
export type ParamDescriptor = {
  path: string; role: string; index: number; original: number; editable: boolean; label: string;
  unit?: string | null; minimum: number; maximum: number; integer: boolean; reason?: string | null;
};
export type ModifiedResult = {
  status: string;
  summary?: Record<string, any>;
  curve?: { dates: string[]; returnPct: number[] };
  contributors?: { top: any[]; bottom: any[]; hidden?: string };
};
export type ModifiedError = { code: string; reason?: string; retryAfterSeconds?: number };

const DEBOUNCE_MS = 600;

/** 입력 문자열 한 칸의 형식·범위 검사. 오류 문구(없으면 null)와 값. */
export function checkInput(raw: string, p: ParamDescriptor): { value?: number; error?: string } {
  const text = raw.trim();
  const value = text === "" ? NaN : Number(text);
  if (!Number.isFinite(value)) return { error: t("숫자를 입력해 주세요.") };
  if (value < p.minimum || value > p.maximum) return { error: t("{0} ~ {1} 범위의 값을 입력해 주세요.", p.minimum, p.maximum) };
  if (p.integer && !Number.isInteger(value)) return { error: t("정수를 입력해 주세요.") };
  return { value };
}

export function useModifiedSimulation(args: {
  publicId: string; baseSnapshotHash: string; dataAsOf: string; params: ParamDescriptor[];
}) {
  const { publicId, baseSnapshotHash, dataAsOf, params } = args;
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ModifiedResult | null>(null);
  const [error, setError] = useState<ModifiedError | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // 검사 통과한 '원본과 다른' 값만 요청 대상이다.
  const { overrides, errors } = useMemo(() => {
    const overrides: { path: string; value: number }[] = [];
    const errors: Record<string, string> = {};
    for (const p of params) {
      const raw = inputs[p.path];
      if (raw === undefined) continue;
      const checked = checkInput(raw, p);
      if (checked.error) errors[p.path] = checked.error;
      else if (checked.value !== p.original) overrides.push({ path: p.path, value: checked.value as number });
    }
    return { overrides, errors };
  }, [inputs, params]);
  const hasErrors = Object.keys(errors).length > 0;
  const key = JSON.stringify(overrides);

  useEffect(() => {
    const id = ++latest.current;                      // 새 입력이 오면 이전 요청의 응답은 버린다
    setError(null);
    if (hasErrors || overrides.length === 0) {
      setResult(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/strategy-simulation/${encodeURIComponent(publicId)}/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ overrides, baseSnapshotHash, dataAsOf }),
          signal: controller.signal,
          cache: "no-store",
        });
        const body = await res.json().catch(() => null);
        if (id !== latest.current) return;
        if (res.ok && body && typeof body.status === "string") {
          setResult(body);
        } else {
          setResult(null);
          setError({ code: body?.code ?? "FAILED", reason: body?.reason, retryAfterSeconds: body?.retryAfterSeconds });
        }
      } catch (e) {
        if (id === latest.current && (e as Error)?.name !== "AbortError") {
          setResult(null);
          setError({ code: "FAILED" });
        }
      } finally {
        if (id === latest.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // key가 overrides의 내용을 대신한다(참조가 매 렌더 바뀌어도 같은 값이면 다시 부르지 않는다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, hasErrors, publicId, baseSnapshotHash, dataAsOf]);

  const setInput = useCallback((path: string, value: string) => setInputs((prev) => ({ ...prev, [path]: value })), []);
  const reset = useCallback(() => setInputs({}), []);

  return { inputs, setInput, reset, errors, result, error, loading, changed: overrides.length };
}
