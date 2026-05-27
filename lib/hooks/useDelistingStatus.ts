import { useEffect, useState } from 'react';
import type { ListingStatusValue } from '@/lib/listing-status';

export interface SymbolListingDetail {
  listingStatus: ListingStatusValue;
  lastTradableDate: string | null;
  delistingDate: string | null;
  suspensionReason: string | null;
}

interface DelistingStatusState {
  delisted: Set<string>;
  warning: Set<string>;
  tradingSuspended: Set<string>;
  delistingScheduled: Set<string>;
  delistingReview: Set<string>;
  details: Record<string, SymbolListingDetail>;
  names: Record<string, string>;
}

const EMPTY: DelistingStatusState = {
  delisted: new Set(),
  warning: new Set(),
  tradingSuspended: new Set(),
  delistingScheduled: new Set(),
  delistingReview: new Set(),
  details: {},
  names: {},
};

export function useDelistingStatus(symbols?: string[]): DelistingStatusState {
  const [status, setStatus] = useState<DelistingStatusState>(EMPTY);

  useEffect(() => {
    const query = symbols?.length ? `?symbols=${symbols.join(',')}` : '';
    fetch(`/api/market/delisting-status${query}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setStatus({
          delisted:           new Set(data.delisted ?? []),
          warning:            new Set(data.warning ?? []),
          tradingSuspended:   new Set(data.tradingSuspended ?? []),
          delistingScheduled: new Set(data.delistingScheduled ?? []),
          delistingReview:    new Set(data.delistingReview ?? []),
          details:            data.details ?? {},
          names:              data.names ?? {},
        });
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols?.join(',')]);

  return status;
}

// 단일 심볼의 ListingStatus 파생 헬퍼
export function resolveListingStatus(
  symbol: string,
  status: DelistingStatusState
): ListingStatusValue {
  if (status.delisted.has(symbol))           return 'DELISTED';
  if (status.delistingScheduled.has(symbol)) return 'DELISTING_SCHEDULED';
  if (status.tradingSuspended.has(symbol))   return 'TRADING_SUSPENDED';
  if (status.delistingReview.has(symbol))    return 'DELISTING_REVIEW';
  if (status.warning.has(symbol))            return 'WARNING';
  return 'NORMAL';
}
