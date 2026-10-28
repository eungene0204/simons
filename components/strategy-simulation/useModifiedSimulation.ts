"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@/lib/i18n";

// 방문자 파라미터 수정 → '적용'을 눌렀을 때 실제 재백테스트. 입력 중인 값(inputs)과 적용한 값(applied)을 나눠 두고,
// 마지막 적용만 유효하며(앞선 요청은 취소·무시) 원본 결과는 읽기만 한다.
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
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ModifiedResult | null>(null);
  const [error, setError] = useState<ModifiedError | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // 입력 중인 값의 형식·범위 오류는 바로 보인다.
  const errors = useMemo(() => {
    const errors: Record<string, string> = {};
    for (const p of params) {
      const raw = inputs[p.path];
      const checked = raw === undefined ? null : checkInput(raw, p);
      if (checked?.error) errors[p.path] = checked.error;
    }
    return errors;
  }, [inputs, params]);
  const hasErrors = Object.keys(errors).length > 0;

  // 요청 대상은 적용한 값 중 검사를 통과한 '원본과 다른' 값뿐이다.
  const overrides = useMemo(() => {
    const out: { path: string; value: number }[] = [];
    for (const p of params) {
      const raw = applied[p.path];
      if (raw === undefined) continue;
      const checked = checkInput(raw, p);
      if (!checked.error && checked.value !== p.original) out.push({ path: p.path, value: checked.value as number });
    }
    return out;
  }, [applied, params]);
  const key = JSON.stringify(overrides);

  // 적용 후 입력을 더 고치면(또는 아직 적용 전이면) 적용 버튼이 켜진다.
  const dirty = useMemo(() => {
    const paths = new Set([...Object.keys(inputs), ...Object.keys(applied)]);
    return [...paths].some((path) => (inputs[path] ?? "") !== (applied[path] ?? ""));
  }, [inputs, applied]);

  useEffect(() => {
    const id = ++latest.current;                      // 새 입력이 오면 이전 요청의 응답은 버린다
    setError(null);
    if (overrides.length === 0) {
      setResult(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    void (async () => {
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
    })();
    return () => controller.abort();
    // key가 overrides의 내용을 대신한다(참조가 매 렌더 바뀌어도 같은 값이면 다시 부르지 않는다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, publicId, baseSnapshotHash, dataAsOf]);

  const setInput = useCallback((path: string, value: string) => setInputs((prev) => ({ ...prev, [path]: value })), []);
  const apply = useCallback(() => {
    if (!hasErrors) setApplied(inputs);
  }, [hasErrors, inputs]);
  const reset = useCallback(() => {
    setInputs({});
    setApplied({});
  }, []);

  return { inputs, setInput, apply, reset, errors, dirty, result, error, loading, changed: overrides.length };
}
