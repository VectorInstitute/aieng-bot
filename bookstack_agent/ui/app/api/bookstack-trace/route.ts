import { NextRequest, NextResponse } from 'next/server'
import { isAuthenticated } from '@/lib/session'

/**
 * Expected trace path format:
 *   data/bookstack/traces/YYYY-MM-DD/XXXXXXXX-HHMMSS.json
 *
 * Groups: (1) date segment, (2) filename segment.
 * Matching strictly here means we never interpolate raw user input into the URL —
 * only regex-captured, URL-encoded segments are used.
 */
const TRACE_PATH_RE =
  /^data\/bookstack\/traces\/(\d{4}-\d{2}-\d{2})\/([a-zA-Z0-9]{1,8}-\d{6}\.json)$/

const GCS_BASE =
  'https://storage.googleapis.com/bot-dashboard-vectorinstitute/data/bookstack/traces'

/**
 * Proxy authenticated requests for per-query trace files from GCS.
 *
 * GET /api/bookstack-trace?path=data/bookstack/traces/YYYY-MM-DD/SESSION-HHMMSS.json
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const rawPath = req.nextUrl.searchParams.get('path')
  if (!rawPath) {
    return NextResponse.json({ error: 'Missing path parameter' }, { status: 400 })
  }

  // Parse the path with a strict regex — only the captured groups are used below.
  // encodeURIComponent on each segment prevents any residual injection.
  const match = rawPath.trim().match(TRACE_PATH_RE)
  if (!match) {
    return NextResponse.json({ error: 'Invalid trace path' }, { status: 400 })
  }

  const date = encodeURIComponent(match[1])
  const filename = encodeURIComponent(match[2])
  const url = `${GCS_BASE}/${date}/${filename}`

  try {
    const res = await fetch(url, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ error: 'Trace not found' }, { status: res.status })
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: 'Failed to fetch trace' }, { status: 500 })
  }
}
