import { NextRequest, NextResponse } from 'next/server'
import { authConfig, isEmailAllowed } from '@/lib/auth-config'
import { getSession } from '@/lib/session'

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const code = searchParams.get('code')
    const state = searchParams.get('state')

    // Use configured app URL for redirects
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.url

    if (!code || !state) {
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=missing_params', baseUrl))
    }

    // Validate state
    const session = await getSession()
    if (state !== session.state) {
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=invalid_state', baseUrl))
    }

    const codeVerifier = session.codeVerifier

    if (!codeVerifier) {
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=missing_verifier', baseUrl))
    }

    // Exchange code for tokens
    const tokenResponse = await fetch(authConfig.google.tokenEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
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
      const error = await tokenResponse.text()
      console.error('Token exchange failed:', error)
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=token_exchange_failed', baseUrl))
    }

    const tokens = await tokenResponse.json()

    // Fetch user info
    const userInfoResponse = await fetch(authConfig.google.userInfoEndpoint, {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
      },
    })

    if (!userInfoResponse.ok) {
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=userinfo_failed', baseUrl))
    }

    const userInfo = await userInfoResponse.json()

    // Validate email domain
    if (!isEmailAllowed(userInfo.email)) {
      return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=unauthorized_domain', baseUrl))
    }

    // Save session
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

    // Clear PKCE data
    delete session.codeVerifier
    delete session.state

    await session.save()

    return NextResponse.redirect(new URL('/aieng-bot-maintain', baseUrl))
  } catch (error) {
    console.error('Callback error:', error)
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.url
    return NextResponse.redirect(new URL('/aieng-bot-maintain/login?error=unknown', baseUrl))
  }
}
