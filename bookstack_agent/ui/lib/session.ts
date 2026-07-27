import { getIronSession, IronSession, SessionOptions } from 'iron-session'
import { cookies } from 'next/headers'
import type { SessionData } from './types'

function getSessionPassword(): string {
  const secret = process.env.SESSION_SECRET
  if (!secret || secret.length < 32) {
    throw new Error('SESSION_SECRET must be set to a value of at least 32 characters')
  }
  return secret
}

const sessionOptions: Omit<SessionOptions, 'password'> = {
  cookieName: 'aieng_bot_bookstack_session',
  cookieOptions: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    sameSite: 'lax',
    path: '/aieng-bot',
    maxAge: 60 * 60 * 24 * 7, // 7 days
  },
}

export async function getSession(): Promise<IronSession<SessionData>> {
  const cookieStore = await cookies()
  return getIronSession<SessionData>(cookieStore, {
    ...sessionOptions,
    password: getSessionPassword(),
  })
}

export async function isAuthenticated(): Promise<boolean> {
  const session = await getSession()
  return session.isAuthenticated === true && !!session.user
}

export async function getCurrentUser() {
  const session = await getSession()
  if (!session.isAuthenticated || !session.user) return null
  return session.user
}
