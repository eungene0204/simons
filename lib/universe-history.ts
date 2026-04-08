import { promises as fs } from "fs";
import path from "path";
import type { UniverseHistoryEntry, UniverseHistoryStore, UniverseOverview } from "@/types/universe";
import { loadStockList } from "@/lib/krx-stocks";

const HISTORY_FILE = path.join(process.cwd(), "data", "universe-history.json");

function emptyStore(): UniverseHistoryStore {
  return {
    updatedAt: null,
    entries: [],
  };
}

function sortEntries(entries: UniverseHistoryEntry[]): UniverseHistoryEntry[] {
  return [...entries].sort((a, b) => {
    if (a.date !== b.date) return b.date.localeCompare(a.date);
    return b.syncedAt.localeCompare(a.syncedAt);
  });
}

export async function loadUniverseHistory(): Promise<UniverseHistoryStore> {
  try {
    const raw = await fs.readFile(HISTORY_FILE, "utf-8");
    const parsed = JSON.parse(raw) as Partial<UniverseHistoryStore>;
    const entries = Array.isArray(parsed.entries) ? sortEntries(parsed.entries as UniverseHistoryEntry[]) : [];
    return {
      updatedAt: parsed.updatedAt ?? null,
      entries,
    };
  } catch {
    return emptyStore();
  }
}

export async function getUniverseOverview(): Promise<UniverseOverview> {
  const history = await loadUniverseHistory();
  const latest = history.entries[0] ?? null;
  if (!latest) {
    const stocks = await loadStockList();
    return {
      currentTotal: stocks.length,
      currentKospi: stocks.filter((stock) => stock.market === "KOSPI").length,
      currentKosdaq: stocks.filter((stock) => stock.market === "KOSDAQ").length,
      latest: null,
      recent: [],
    };
  }

  return {
    currentTotal: latest?.totalCount ?? 0,
    currentKospi: latest?.kospiCount ?? 0,
    currentKosdaq: latest?.kosdaqCount ?? 0,
    latest,
    recent: history.entries.slice(0, 7),
  };
}
