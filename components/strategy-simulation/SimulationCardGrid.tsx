"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Spinner } from "phosphor-react";
import { t } from "@/lib/i18n";
import { pct, signTone, won } from "./format";
import { SimulationMiniChart, type SimulationCurve } from "./SimulationMiniChart";

// 공개 전략 카드 목록 — 저장된 원본 결과만 보여 준다. 정렬은 이름순이며 성과 순위·추천은 없다.
export type SimulationCard = {
  publicId: string;
  name: string;
  description: string | null;
  status: "pending" | "refreshing" | "ready" | "no_trades" | "unavailable" | "failed";
  reason?: string;
  window?: { actualStart?: string; actualEnd?: string; dataAsOf?: string; limited?: boolean };
  summary?: { totalReturnPct?: number; totalProfit?: number; maxDrawdownPct?: number };
  curve?: SimulationCurve;
};

function reasonText(reason?: string): string {
  switch (reason) {
    case "NO_EXECUTABLE_SNAPSHOT": return t("저장된 실행 조건이 없어 계산할 수 없습니다.");
    case "MISSING_RUN_CONDITION": return t("초기 자본 또는 수수료·슬리피지 조건이 저장되어 있지 않습니다.");
    case "UNSUPPORTED_CONTRIBUTIONS": return t("적립식·인출 설정이 있는 전략은 지원하지 않습니다.");
    case "UNSUPPORTED_REGION": return t("미국 시장 전략은 지원하지 않습니다.");
    case "UNSUPPORTED_AI_SIGNAL": return t("AI 신호를 쓰는 전략은 지원하지 않습니다.");
    default: return t("저장된 조건을 실행할 수 없습니다.");
  }
}

function CardBody({ card }: { card: SimulationCard }) {
  const { status, summary } = card;
  if (status === "pending") return <p className="text-sm font-bold text-gray-400">{t("원본 결과를 계산하고 있습니다.")}</p>;
  if (status === "failed") return <p className="text-sm font-bold text-gray-400">{t("계산에 실패해 잠시 후 다시 시도합니다.")}</p>;
  if (status === "unavailable") return <p className="text-sm font-bold text-gray-400">{reasonText(card.reason)}</p>;
  if (!summary || summary.totalReturnPct === undefined) return null;
  return (
    <>
      {card.curve && <SimulationMiniChart curve={card.curve} />}
      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-[var(--text-label)]">{t("누적 수익률")}</dt>
          <dd className={`mt-0.5 text-sm font-black ${signTone(summary.totalReturnPct)}`}>{pct(summary.totalReturnPct)}</dd>
        </div>
        <div>
          <dt className="text-[var(--text-label)]">{t("총 손익")}</dt>
          <dd className={`mt-0.5 text-sm font-black ${signTone(summary.totalProfit ?? 0)}`}>{won(summary.totalProfit ?? 0)}</dd>
        </div>
        <div>
          <dt className="text-[var(--text-label)]">{t("최대 낙폭")}</dt>
          <dd className="mt-0.5 text-sm font-black text-white">{pct(summary.maxDrawdownPct ?? 0)}</dd>
        </div>
      </dl>
      {status === "no_trades" && <p className="mt-2 text-xs font-bold text-gray-400">{t("이 기간에는 거래가 없었습니다.")}</p>}
    </>
  );
}

export function SimulationCardGrid({ onOpen }: { onOpen?: (publicId: string) => void }) {
  const [items, setItems] = useState<SimulationCard[]>([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (q: string, nextPage: number) => {
    const id = ++latest.current;
    setLoading(true);
    setFailed(false);
    try {
      const params = new URLSearchParams({ page: String(nextPage) });
      if (q) params.set("q", q);
      const res = await fetch(`/api/strategy-simulation?${params}`, { cache: "no-store" });
      const body = await res.json().catch(() => null);
      if (id !== latest.current) return;           // 더 새 요청이 있으면 이 응답은 버린다
      if (!res.ok || !Array.isArray(body?.items)) throw new Error("LIST_FAILED");
      setItems((prev) => (nextPage === 1 ? body.items : [...prev, ...body.items]));
      setPage(nextPage);
      setHasNext(!!body.hasNext);
    } catch {
      if (id === latest.current) setFailed(true);
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(query, 1);
  }, [load, query]);

  return (
    <div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(input.trim());
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={50}
          placeholder={t("전략 이름 검색")}
          aria-label={t("전략 이름 검색")}
          className="min-w-0 flex-1 rounded-lg border border-white/[0.12] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder:text-[var(--text-placeholder)] focus-visible:outline-none focus-visible:border-white/40"
        />
        <button type="submit" className="rounded-lg bg-[var(--chat-accent)] px-4 py-2 text-sm font-black text-[var(--chat-accent-ink)]">
          {t("검색")}
        </button>
      </form>

      {failed && (
        <p role="alert" className="mt-6 text-sm font-bold text-gray-400">
          {t("목록을 불러오지 못했습니다.")}{" "}
          <button type="button" className="underline" onClick={() => void load(query, 1)}>{t("다시 시도")}</button>
        </p>
      )}
      {!failed && !loading && items.length === 0 && (
        <p className="mt-6 text-sm font-bold text-gray-400">{query ? t("검색 결과가 없습니다.") : t("공개된 전략이 아직 없습니다.")}</p>
      )}

      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((card) => (
          <li key={card.publicId}>
            <button
              type="button"
              data-card-id={card.publicId}
              onClick={() => onOpen?.(card.publicId)}
              className="flat-card block h-full w-full rounded-xl p-4 text-left transition-colors hover:bg-white/[0.04]"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-black text-white">{card.name}</h2>
                {card.status === "refreshing" && (
                  <span className="shrink-0 rounded bg-white/[0.08] px-1.5 py-0.5 text-[11px] font-bold text-gray-300">{t("갱신 중")}</span>
                )}
              </div>
              {card.description && <p className="mt-1 line-clamp-2 text-xs text-gray-400">{card.description}</p>}
              <div className="mt-3"><CardBody card={card} /></div>
              {card.window?.actualStart && (
                <p className="mt-3 text-[11px] text-[var(--text-label)]">
                  {card.window.actualStart} ~ {card.window.actualEnd} · {t("데이터 기준일 {0}", card.window.dataAsOf)}
                  {card.window.limited && ` · ${t("데이터 부족으로 요청 기간보다 짧음")}`}
                </p>
              )}
            </button>
          </li>
        ))}
      </ul>

      {loading && (
        <p role="status" className="mt-6 flex items-center gap-2 text-sm font-bold text-gray-400">
          <Spinner size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {t("불러오는 중")}
        </p>
      )}
      {hasNext && !loading && (
        <button type="button" onClick={() => void load(query, page + 1)} className="mt-6 rounded-lg border border-white/[0.12] px-4 py-2 text-sm font-bold text-white">
          {t("더 보기")}
        </button>
      )}
    </div>
  );
}
