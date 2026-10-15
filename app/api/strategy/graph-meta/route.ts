import { NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

export const dynamic = 'force-dynamic'

// Read-only public indicator metadata for the strategy graph. The backend extracts it
// deterministically from the registry/ontology; it holds no user data or admin diagnostics,
// so no session is required (same exposure as /api/strategy/compile). The admin ontology
// endpoint is intentionally not used here.
export async function GET() {
  try {
    const res = await fetchBackend('/strategy/graph-meta', { timeoutMs: 15_000 })
    if (!res.ok) {
      return NextResponse.json({ error: 'graph-meta backend error' }, { status: 502 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'graph-meta backend unreachable' }, { status: 502 })
  }
}
