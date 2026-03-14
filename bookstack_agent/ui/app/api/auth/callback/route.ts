import { NextRequest, NextResponse } from 'next/server'
import { authConfig, isEmailAllowed } from '@/lib/auth-config'
import { getSession } from '@/lib/session'
import { cookies } from 'next/headers'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const code = searchParams.get('code')
    const state = searchParams.get('state')

    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || new URL(request.url).origin

    if (!code || !state) {
      return NextResponse.redirect(new URL('/aieng-bot/login?error=missing_params', baseUrl))
    }

    const cookieStore = await cookies()
    const storedState = cookieStore.get('oauth_state')?.value

    if (state !== storedState) {
      return NextResponse.redirect(new URL('/aieng-bot/login?error=invalid_state', baseUrl))
    }

    const codeVerifier = cookieStore.get('pkce_verifier')?.value

    if (!codeVerifier) {
      return NextResponse.redirect(new URL('/aieng-bot/login?error=missing_verifier', baseUrl))
    }

    const tokenResponse = await fetch(authConfig.google.tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: authConfig.google.clientId,
        client_secret: authConfig.google.clientSecret,
        redirect_uri: authConfig.google.redirectUri,
        grant_type: 'authorization_code',
        code_verifier: codeVerifier,
      }),
    })

    if (!tokenResponse.ok) {
      console.error('Token exchange failed:', await tokenResponse.text())
      return NextResponse.redirect(new URL('/aieng-bot/login?error=token_exchange_failed', baseUrl))
    }

    const tokens = await tokenResponse.json()

    const userInfoResponse = await fetch(authConfig.google.userInfoEndpoint, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })

    if (!userInfoResponse.ok) {
      return NextResponse.redirect(new URL('/aieng-bot/login?error=userinfo_failed', baseUrl))
    }

    const userInfo = await userInfoResponse.json()

    if (!isEmailAllowed(userInfo.email)) {
      return NextResponse.redirect(new URL('/aieng-bot/login?error=unauthorized_domain', baseUrl))
    }

    const session = await getSession()
    session.isAuthenticated = true
    session.user = {
      email: userInfo.email,
      name: userInfo.name,
      picture: userInfo.picture,
    }
    session.tokens = {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_at: Date.now() + tokens.expires_in * 1000,
    }
    await session.save()

    const redirectResponse = NextResponse.redirect(new URL('/aieng-bot', baseUrl))
    redirectResponse.cookies.delete('pkce_verifier')
    redirectResponse.cookies.delete('oauth_state')

    return redirectResponse
  } catch (error) {
    console.error('Callback error:', error)
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.url
    return NextResponse.redirect(new URL('/aieng-bot/login?error=unknown', baseUrl))
  }
}
