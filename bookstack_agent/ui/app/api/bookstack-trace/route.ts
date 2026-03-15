import { NextRequest, NextResponse } from 'next/server'
import { isAuthenticated } from '@/lib/session'

const GCS_BUCKET_URL = 'https://storage.googleapis.com/bot-dashboard-vectorinstitute'

/**
 * Sanitize a user-supplied trace path.
 *
 * Accepts only relative paths (no leading slash, no absolute URLs), rejects
 * traversal segments (. and ..), and enforces the required prefix so only
 * objects under data/bookstack/traces/ can ever be fetched.
 *
 * Returns the normalized path, or null if the input is invalid.
 */
function sanitizeTracePath(rawPath: string | null): string | null {
  if (!rawPath) return null

  const trimmed = rawPath.trim()
  const lower = trimmed.toLowerCase()

  // Reject absolute URLs or absolute-style paths
  if (
    trimmed.startsWith('/') ||
    trimmed.startsWith('\\') ||
    lower.startsWith('http://') ||
    lower.startsWith('https://')
  ) {
    return null
  }

  // Split, drop empty segments, reject traversal and backslash-containing segments
  const segments = trimmed.split('/').filter((s) => s.length > 0)
  for (const seg of segments) {
    if (seg === '.' || seg === '..' || seg.includes('\\')) {
      return null
    }
  }

  const normalized = segments.join('/')

  if (!normalized.startsWith('data/bookstack/traces/')) {
    return null
  }

  return normalized
}

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

  const rawPath = req.nextUrl.searchParams.get('path')
  if (!rawPath) {
    return NextResponse.json({ error: 'Missing path parameter' }, { status: 400 })
  }

  const safePath = sanitizeTracePath(rawPath)
  if (!safePath) {
    return NextResponse.json({ error: 'Invalid trace path' }, { status: 400 })
  }

  try {
    const res = await fetch(`${GCS_BUCKET_URL}/${safePath}`, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ error: 'Trace not found' }, { status: res.status })
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: 'Failed to fetch trace' }, { status: 500 })
  }
}
