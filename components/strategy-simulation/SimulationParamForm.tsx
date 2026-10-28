"use client";

import { t } from "@/lib/i18n";
import type { ParamDescriptor } from "./useModifiedSimulation";

// 서버가 내리는 수정 불가 사유 코드 → 안내 문구(코드는 화면에 노출하지 않는다).
function reasonText(code: string): string {
  if (code === "UNSUPPORTED_INDICATOR") return t("이 지표는 값을 바꿀 수 없습니다.");
  if (code === "NO_RANGE_METADATA") return t("허용 범위가 정해지지 않아 값을 바꿀 수 없습니다.");
  return t("값을 바꿀 수 없습니다.");
}

// 지표 파라미터 수정 폼 — 숫자 칸과 적용 버튼. 범위·정수 검사는 입력 즉시, 계산은 적용을 눌렀을 때만 한다.
export function SimulationParamForm(props: {
  params: ParamDescriptor[];
  inputs: Record<string, string>;
  errors: Record<string, string>;
  onChange: (path: string, value: string) => void;
  onApply: () => void;
  onReset: () => void;
  dirty: boolean;
  changed: number;
}) {
  const { params, inputs, errors, onChange, onApply, onReset, dirty, changed } = props;
  if (params.length === 0) return <p className="text-xs text-gray-400">{t("수정할 수 있는 지표 값이 없습니다.")}</p>;
  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        {params.map((p) => {
          const id = `param-${p.path}`;
          const role = p.role === "entry" ? t("매수") : t("매도");
          return (
            <div key={p.path}>
              <label htmlFor={id} className="text-[11px] font-bold text-[var(--text-label)]">
                {role} {p.index + 1} · {p.reason === "UNSUPPORTED_INDICATOR" ? t("지원하지 않는 지표") : p.label}
                {p.unit ? ` (${p.unit})` : ""}
              </label>
              <input
                id={id}
                inputMode="decimal"
                disabled={!p.editable}
                value={inputs[p.path] ?? String(p.original)}
                onChange={(e) => onChange(p.path, e.target.value)}
                aria-invalid={!!errors[p.path]}
                className="mt-1 w-full rounded-lg border border-white/[0.12] bg-white/[0.04] px-3 py-2 text-sm text-white focus-visible:outline-none focus-visible:border-white/40 disabled:opacity-50"
              />
              {errors[p.path] && <p role="alert" className="mt-1 text-[11px] text-gray-300">{errors[p.path]}</p>}
              {!p.editable && p.reason && <p className="mt-1 text-[11px] text-gray-400">{reasonText(p.reason)}</p>}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onApply}
          disabled={!dirty || Object.keys(errors).length > 0}
          className="rounded-lg bg-[var(--chat-accent)] px-4 py-1.5 text-sm font-black text-[var(--chat-accent-ink)] disabled:opacity-40"
        >
          {t("적용")}
        </button>
        <button
          type="button"
          onClick={onReset}
          disabled={Object.keys(inputs).length === 0}
          className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-40"
        >
          {t("원본 값으로 초기화")}
        </button>
      </div>
      {changed > 0 && <span className="mt-2 block text-xs text-gray-400">{t("{0}개 값을 바꿔 계산합니다.", changed)}</span>}
    </div>
  );
}
