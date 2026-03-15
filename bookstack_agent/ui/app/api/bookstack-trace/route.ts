import { NextRequest, NextResponse } from 'next/server'
import { isAuthenticated } from '@/lib/session'

const GCS_BUCKET_URL = 'https://storage.googleapis.com/bot-dashboard-vectorinstitute'

/**
 * Proxy authenticated requests for per-query trace files from GCS.
 *
 * GET /api/bookstack-trace?path=data/bookstack/traces/...
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const tracePath = req.nextUrl.searchParams.get('path')
  if (!tracePath) {
    return NextResponse.json({ error: 'Missing path parameter' }, { status: 400 })
  }

  // Restrict to expected prefix to prevent arbitrary GCS reads
  if (!tracePath.startsWith('data/bookstack/traces/')) {
    return NextResponse.json({ error: 'Invalid trace path' }, { status: 400 })
  }

  try {
    const res = await fetch(`${GCS_BUCKET_URL}/${tracePath}`, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ error: 'Trace not found' }, { status: res.status })
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: 'Failed to fetch trace' }, { status: 500 })
  }
}
