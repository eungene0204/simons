// Watchlist utility functions for managing user's watchlist
// Uses localStorage to persist watchlist data

export interface WatchlistSymbol {
  symbol: string;
  name: string;
  addedAt: string;
  groupId?: string;
}

export interface WatchlistGroup {
  id: string;
  name: string;
  color?: string;
  createdAt: string;
}

const WATCHLIST_STORAGE_KEY = "watchlist_symbols";
const WATCHLIST_GROUPS_STORAGE_KEY = "watchlist_groups";

/**
 * Get all watchlist symbols from localStorage
 */
export function getWatchlistSymbols(): WatchlistSymbol[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (!stored) {
      return [];
    }
    return JSON.parse(stored);
  } catch (error) {
    console.error("Failed to load watchlist:", error);
    return [];
  }
}

/**
 * Add a symbol to watchlist
 */
export function addToWatchlist(symbol: string, name: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const watchlist = getWatchlistSymbols();
    
    // Check if already exists
    if (watchlist.some((item) => item.symbol === symbol)) {
      return false; // Already in watchlist
    }

    const newItem: WatchlistSymbol = {
      symbol,
      name,
      addedAt: new Date().toISOString(),
    };

    watchlist.push(newItem);
    localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlist));
    return true;
  } catch (error) {
    console.error("Failed to add to watchlist:", error);
    return false;
  }
}

/**
 * Add multiple symbols to watchlist
 */
export function addMultipleToWatchlist(
  items: Array<{ symbol: string; name: string }>
): number {
  if (typeof window === "undefined") {
    return 0;
  }

  try {
    const watchlist = getWatchlistSymbols();
    const existingSymbols = new Set(watchlist.map((item) => item.symbol));
    let addedCount = 0;

    items.forEach((item) => {
      // Skip if already exists
      if (!existingSymbols.has(item.symbol)) {
        const newItem: WatchlistSymbol = {
          symbol: item.symbol,
          name: item.name,
          addedAt: new Date().toISOString(),
        };
        watchlist.push(newItem);
        existingSymbols.add(item.symbol);
        addedCount++;
      }
    });

    if (addedCount > 0) {
      localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlist));
    }

    return addedCount;
  } catch (error) {
    console.error("Failed to add multiple to watchlist:", error);
    return 0;
  }
}

/**
 * Remove a symbol from watchlist
 */
export function removeFromWatchlist(symbol: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const watchlist = getWatchlistSymbols();
    const filtered = watchlist.filter((item) => item.symbol !== symbol);
    localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(filtered));
    return true;
  } catch (error) {
    console.error("Failed to remove from watchlist:", error);
    return false;
  }
}

/**
 * Check if a symbol is in watchlist
 */
export function isInWatchlist(symbol: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  const watchlist = getWatchlistSymbols();
  return watchlist.some((item) => item.symbol === symbol);
}

/**
 * Get all watchlist groups from localStorage
 */
export function getWatchlistGroups(): WatchlistGroup[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = localStorage.getItem(WATCHLIST_GROUPS_STORAGE_KEY);
    if (!stored) {
      return [];
    }
    return JSON.parse(stored);
  } catch (error) {
    console.error("Failed to load watchlist groups:", error);
    return [];
  }
}

/**
 * Create a new watchlist group
 */
export function createWatchlistGroup(name: string, color?: string): WatchlistGroup {
  if (typeof window === "undefined") {
    throw new Error("Cannot create group on server");
  }

  try {
    const groups = getWatchlistGroups();
    const newGroup: WatchlistGroup = {
      id: `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name,
      color: color || "#3B82F6",
      createdAt: new Date().toISOString(),
    };

    groups.push(newGroup);
    localStorage.setItem(WATCHLIST_GROUPS_STORAGE_KEY, JSON.stringify(groups));
    return newGroup;
  } catch (error) {
    console.error("Failed to create watchlist group:", error);
    throw error;
  }
}

/**
 * Update a watchlist group
 */
export function updateWatchlistGroup(groupId: string, updates: Partial<Omit<WatchlistGroup, "id" | "createdAt">>): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const groups = getWatchlistGroups();
    const index = groups.findIndex((g) => g.id === groupId);
    if (index === -1) {
      return false;
    }

    groups[index] = { ...groups[index], ...updates };
    localStorage.setItem(WATCHLIST_GROUPS_STORAGE_KEY, JSON.stringify(groups));
    return true;
  } catch (error) {
    console.error("Failed to update watchlist group:", error);
    return false;
  }
}

/**
 * Delete a watchlist group
 */
export function deleteWatchlistGroup(groupId: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const groups = getWatchlistGroups();
    const filtered = groups.filter((g) => g.id !== groupId);
    localStorage.setItem(WATCHLIST_GROUPS_STORAGE_KEY, JSON.stringify(filtered));

    // Remove groupId from all symbols in this group
    const watchlist = getWatchlistSymbols();
    const updated = watchlist.map((item) => 
      item.groupId === groupId ? { ...item, groupId: undefined } : item
    );
    localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(updated));

    return true;
  } catch (error) {
    console.error("Failed to delete watchlist group:", error);
    return false;
  }
}

/**
 * Assign a symbol to a group
 */
export function assignSymbolToGroup(symbol: string, groupId: string | undefined): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const watchlist = getWatchlistSymbols();
    const index = watchlist.findIndex((item) => item.symbol === symbol);
    if (index === -1) {
      return false;
    }

    watchlist[index] = { ...watchlist[index], groupId };
    localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlist));
    return true;
  } catch (error) {
    console.error("Failed to assign symbol to group:", error);
    return false;
  }
}

