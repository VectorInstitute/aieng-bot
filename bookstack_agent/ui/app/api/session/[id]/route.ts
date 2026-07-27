import { NextRequest, NextResponse } from 'next/server'
import { isAuthenticated } from '@/lib/session'

/**
 * Proxy route — forwards DELETE /api/session/:id to the FastAPI backend so
 * "New chat" clears the server-side conversation history.
 */

const SESSION_ID_RE = /^[a-zA-Z0-9-]{1,64}$/

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const { id } = await params
  if (!SESSION_ID_RE.test(id)) {
    return NextResponse.json({ error: 'Invalid session id' }, { status: 400 })
  }

  const backendUrl = process.env.BOOKSTACK_API_URL ?? 'http://localhost:8000'

  try {
    const res = await fetch(
      `${backendUrl}/api/session/${encodeURIComponent(id)}`,
      { method: 'DELETE' },
    )
    if (!res.ok) {
      return NextResponse.json(
        { error: 'Backend error' },
        { status: res.status },
      )
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json(
      { error: 'Could not reach backend' },
      { status: 502 },
    )
  }
}
