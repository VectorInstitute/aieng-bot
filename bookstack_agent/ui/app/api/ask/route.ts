/**
 * Proxy route — forwards POST /api/ask to the FastAPI backend and streams
 * the SSE response back to the browser unchanged.
 *
 * Using a server-side proxy keeps BOOKSTACK_API_URL out of the browser and
 * avoids CORS issues between the UI and the Python backend.
 */
import { getCurrentUser } from '@/lib/session'

export const dynamic = 'force-dynamic'

export async function POST(req: Request): Promise<Response> {
  const body = await req.json()

  // Inject the authenticated user's email so the backend can log it.
  const user = await getCurrentUser()
  if (user?.email) {
    body.user_email = user.email
  }

  const backendUrl = process.env.BOOKSTACK_API_URL ?? 'http://localhost:8000'

  let upstream: Response
  try {
    upstream = await fetch(`${backendUrl}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (err) {
    return new Response(
      JSON.stringify({ error: `Could not reach backend: ${err}` }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    )
  }

  if (!upstream.ok) {
    const text = await upstream.text()
    return new Response(text, { status: upstream.status })
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type':    'text/event-stream',
      'Cache-Control':   'no-cache',
      'X-Accel-Buffering': 'no',
      Connection:        'keep-alive',
    },
  })
}
