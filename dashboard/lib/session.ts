/**
 * Iron Session configuration for secure, encrypted cookies
 */

import { getIronSession, IronSession, SessionOptions } from 'iron-session'
import { cookies } from 'next/headers'
import type { SessionData } from './types'

const sessionOptions: SessionOptions = {
  password: process.env.SESSION_SECRET || 'complex_password_at_least_32_characters_long',
  cookieName: 'aieng_bot_dashboard_session',
  cookieOptions: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    sameSite: 'lax',
    path: '/',  // Changed from '/aieng-bot-maintain' to '/' to ensure cookie is accessible
    maxAge: 60 * 60 * 24 * 7, // 7 days
  },
}

/**
 * Get the current session
 */
export async function getSession(): Promise<IronSession<SessionData>> {
  const cookieStore = await cookies()
  return getIronSession<SessionData>(cookieStore, sessionOptions)
}

/**
 * Check if user is authenticated
 */
export async function isAuthenticated(): Promise<boolean> {
  const session = await getSession()
  return session.isAuthenticated === true && !!session.user
}

/**
 * Get current user or null
 */
export async function getCurrentUser() {
  const session = await getSession()

  if (!session.isAuthenticated || !session.user) {
    return null
  }

  return session.user
}
