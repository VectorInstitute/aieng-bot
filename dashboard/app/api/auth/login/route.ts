import { NextResponse } from 'next/server'
import { authConfig, generatePKCE, generateState } from '@/lib/auth-config'
import { getSession } from '@/lib/session'

export async function GET() {
  try {
    // Generate PKCE parameters
    const { codeVerifier, codeChallenge } = await generatePKCE()
    const state = generateState()

    // Store verifier and state in session
    const session = await getSession()
    session.codeVerifier = codeVerifier
    session.state = state
    await session.save()

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

    return NextResponse.redirect(authUrl)
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 })
  }
}
