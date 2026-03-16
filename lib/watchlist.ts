// Watchlist utility functions - persists data via API (SQLite DB)

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

export async function getWatchlistSymbols(): Promise<WatchlistSymbol[]> {
  try {
    const res = await fetch('/api/watchlist/symbols')
    if (!res.ok) return []
    const data = await res.json()
    return data.map((item: WatchlistSymbol & { addedAt: string | Date }) => ({
      symbol: item.symbol,
      name: item.name,
      addedAt: typeof item.addedAt === 'string' ? item.addedAt : new Date(item.addedAt).toISOString(),
      groupId: item.groupId,
    }))
  } catch {
    return []
  }
}

export async function addToWatchlist(symbol: string, name: string): Promise<boolean> {
  try {
    const res = await fetch('/api/watchlist/symbols', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, name }),
    })
    if (!res.ok) return false
    const data = await res.json()
    return data.added === true
  } catch {
    return false
  }
}

export async function addMultipleToWatchlist(
  items: Array<{ symbol: string; name: string }>
): Promise<number> {
  try {
    const results = await Promise.all(items.map((item) => addToWatchlist(item.symbol, item.name)))
    return results.filter(Boolean).length
  } catch {
    return 0
  }
}

export async function removeFromWatchlist(symbol: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/watchlist/symbols/${encodeURIComponent(symbol)}`, {
      method: 'DELETE',
    })
    return res.ok
  } catch {
    return false
  }
}

export async function isInWatchlist(symbol: string): Promise<boolean> {
  const list = await getWatchlistSymbols()
  return list.some((item) => item.symbol === symbol)
}

export async function getWatchlistGroups(): Promise<WatchlistGroup[]> {
  try {
    const res = await fetch('/api/watchlist/groups')
    if (!res.ok) return []
    return await res.json()
  } catch {
    return []
  }
}

export async function createWatchlistGroup(name: string, color?: string): Promise<WatchlistGroup> {
  const res = await fetch('/api/watchlist/groups', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color: color || '#3B82F6' }),
  })
  if (!res.ok) throw new Error('Failed to create group')
  return await res.json()
}

export async function updateWatchlistGroup(
  groupId: string,
  updates: Partial<Omit<WatchlistGroup, 'id' | 'createdAt'>>
): Promise<boolean> {
  try {
    const res = await fetch(`/api/watchlist/groups/${groupId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function deleteWatchlistGroup(groupId: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/watchlist/groups/${groupId}`, {
      method: 'DELETE',
    })
    return res.ok
  } catch {
    return false
  }
}

export async function assignSymbolToGroup(
  symbol: string,
  groupId: string | undefined
): Promise<boolean> {
  try {
    const res = await fetch(`/api/watchlist/symbols/${encodeURIComponent(symbol)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ groupId: groupId ?? null }),
    })
    return res.ok
  } catch {
    return false
  }
}
