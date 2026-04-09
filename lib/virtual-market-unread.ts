import type { VirtualMarketLog } from "@/lib/virtual-market";

export const getSignalReadStorageKey = (accountId: string) =>
  `virtual-market:last-read-log:${accountId}`;

export function getLatestSignalMarker(logs: VirtualMarketLog[]): string | null {
  return logs[0]?.id ?? null;
}

export function calculateUnreadSignalCount(
  logs: VirtualMarketLog[],
  lastReadMarker: string | null
): number {
  if (logs.length === 0) return 0;
  if (!lastReadMarker) return logs.length;

  const markerIndex = logs.findIndex((log) => log.id === lastReadMarker);
  if (markerIndex === -1) return logs.length;
  return markerIndex;
}
