import { NextResponse } from 'next/server'
import { getSession } from '@/lib/session'

export async function GET() {
  try {
    const session = await getSession()

    if (!session.isAuthenticated || !session.user) {
      return NextResponse.json({ authenticated: false }, { status: 401 })
    }

    return NextResponse.json({
      authenticated: true,
      user: session.user,
    })
  } catch (error) {
    console.error('Session check error:', error)
    return NextResponse.json({ error: 'Session check failed' }, { status: 500 })
  }
}
