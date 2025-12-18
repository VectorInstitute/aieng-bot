import { NextResponse } from 'next/server'
import { authConfig, generatePKCE, generateState } from '@/lib/auth-config'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    // Generate PKCE parameters
    const { codeVerifier, codeChallenge } = await generatePKCE()
    const state = generateState()

    // Build authorization URL
    const params = new URLSearchParams({
      client_id: authConfig.google.clientId,
      redirect_uri: authConfig.google.redirectUri,
      response_type: 'code',
      scope: authConfig.google.scopes.join(' '),
      state,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
      access_type: 'offline',
      prompt: 'consent',
    })

    const authUrl = `${authConfig.google.authorizationEndpoint}?${params.toString()}`

    // Store PKCE and state in regular cookies (temporary, for callback)
    const response = NextResponse.redirect(authUrl)
    response.cookies.set('pkce_verifier', codeVerifier, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600, // 10 minutes
      path: '/',
    })
    response.cookies.set('oauth_state', state, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600, // 10 minutes
      path: '/',
    })

    return response
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 })
  }
}
