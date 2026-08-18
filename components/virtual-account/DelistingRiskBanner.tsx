"use client";

import { Warning, X } from "phosphor-react";
import { useState } from "react";
import { daysUntil, getStatusBadgeClasses } from "@/lib/listing-status";
import type { SymbolListingDetail } from "@/lib/hooks/useDelistingStatus";
import { t } from "@/lib/i18n";

interface RiskItem {
  symbol: string;
  name: string;
  listingStatus: string;
  detail: SymbolListingDetail | null;
}

interface DelistingRiskBannerProps {
  items: RiskItem[];
  onForceLiquidate?: (symbol: string) => void;
}

function statusMessage(item: RiskItem): string {
  const name = item.name || item.symbol;
  const detail = item.detail;

  switch (item.listingStatus) {
    case "DELISTED":
      return t("{0}은(는) 상장폐지된 종목입니다. 평가금액이 0원으로 처리됩니다.", name);
    case "DELISTING_SCHEDULED": {
      const days = daysUntil(detail?.lastTradableDate);
      const countdown = days != null && days >= 0 ? t(" ({0}일 후 최종 거래일)", days) : "";
      return t("{0}은(는) 상장폐지 확정 종목입니다. 신규 매수가 불가하며{1} 자동 청산될 예정입니다.", name, countdown);
    }
    case "TRADING_SUSPENDED":
      return t("{0}은(는) 매매거래정지 상태입니다. 거래 재개 전까지 매수/매도가 불가합니다.", name);
    case "DELISTING_REVIEW":
      return t("{0}은(는) 상장적격성 심사 대상입니다. 신규 매수가 제한됩니다.", name);
    case "WARNING":
    case "RISK":
      return t("{0}은(는) 상장폐지 관련 공시가 있는 종목입니다. 주의가 필요합니다.", name);
    default:
      return t("{0}의 상장 상태를 확인하세요.", name);
  }
}

function badgeStyle(status: string): string {
  if (status === "DELISTED" || status === "DELISTING_SCHEDULED") {
    return "bg-red-500/20 text-red-400 border border-red-500/30";
  }
  if (status === "TRADING_SUSPENDED" || status === "DELISTING_REVIEW") {
    return "bg-orange-500/15 text-orange-400 border border-orange-500/25";
  }
  return "bg-yellow-500/15 text-yellow-400 border border-yellow-500/25";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    DELISTED:             "상장폐지",
    DELISTING_SCHEDULED:  "폐지확정",
    TRADING_SUSPENDED:    "거래정지",
    DELISTING_REVIEW:     "심사중",
    WARNING:              "폐지주의",
    RISK:                 "위험",
  };
  return t(labels[status] ?? status);
}

export default function DelistingRiskBanner({ items, onForceLiquidate }: DelistingRiskBannerProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visible = items.filter((i) => !dismissed.has(i.symbol));
  if (visible.length === 0) return null;

  return (
    <div className="border border-yellow-500/20 bg-yellow-500/5 px-4 py-3 space-y-2">
      {visible.map((item) => {
        const days = daysUntil(item.detail?.lastTradableDate);
        return (
          <div key={item.symbol} className="flex items-start gap-3">
            <Warning size={16} className="text-yellow-400 shrink-0 mt-0.5" weight="fill" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`text-[9px] font-black tracking-wide px-1.5 py-0.5 rounded shrink-0 ${badgeStyle(item.listingStatus)}`}
                >
                  {statusLabel(item.listingStatus)}
                </span>
                <span className="text-xs font-bold text-white">{item.name || item.symbol}</span>
                <span className="text-[10px] font-bold text-gray-500">{item.symbol}</span>
                {days != null && days >= 0 && (
                  <span className="text-[10px] font-black text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">
                    D-{days}
                  </span>
                )}
              </div>
              <p className="text-[11px] font-bold text-gray-400 mt-0.5 leading-relaxed">
                {statusMessage(item)}
              </p>
              {item.detail?.suspensionReason && (
                <p className="text-[10px] text-gray-600 mt-0.5 truncate">
                  {t("사유: {0}", item.detail.suspensionReason)}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {(item.listingStatus === "DELISTING_SCHEDULED" || item.listingStatus === "DELISTED") &&
                onForceLiquidate && (
                  <button
                    onClick={() => onForceLiquidate(item.symbol)}
                    className="text-[10px] font-bold px-2 py-0.5 rounded border border-red-500/40 text-red-400 hover:bg-red-500/10 transition-colors duration-200"
                  >
                    {t("강제청산")}
                  </button>
                )}
              <button
                onClick={() => setDismissed((prev) => new Set([...prev, item.symbol]))}
                className="text-gray-600 hover:text-gray-400 transition-colors duration-200"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
