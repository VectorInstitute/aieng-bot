/**
 * Google OAuth authentication configuration
 */

export const authConfig = {
  google: {
    clientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
    clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
    redirectUri: process.env.REDIRECT_URI || '',
    authorizationEndpoint: 'https://accounts.google.com/o/oauth2/v2/auth',
    tokenEndpoint: 'https://oauth2.googleapis.com/token',
    userInfoEndpoint: 'https://www.googleapis.com/oauth2/v2/userinfo',
    scopes: ['openid', 'email', 'profile'],
  },
  allowedDomains: (process.env.ALLOWED_DOMAINS || '').split(',').filter(Boolean),
  sessionSecret: process.env.SESSION_SECRET || '',
}

/**
 * Validate that a user email is from an allowed domain
 */
export function isEmailAllowed(email: string): boolean {
  if (!email) return false

  const emailDomain = email.split('@')[1]?.toLowerCase()

  if (!emailDomain) return false

  return authConfig.allowedDomains.some(
    (domain) => emailDomain === domain.toLowerCase()
  )
}

/**
 * Generate PKCE challenge and verifier
 */
export async function generatePKCE(): Promise<{ codeVerifier: string; codeChallenge: string }> {
  const codeVerifier = generateRandomString(64)
  const codeChallenge = base64URLEncode(await sha256(codeVerifier))

  return { codeVerifier, codeChallenge }
}

/**
 * Generate OAuth state parameter for CSRF protection
 */
export function generateState(): string {
  return generateRandomString(32)
}

// Helper functions
function generateRandomString(length: number): string {
  const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
  let result = ''

  const randomValues = new Uint8Array(length)
  crypto.getRandomValues(randomValues)

  for (let i = 0; i < length; i++) {
    result += charset[randomValues[i] % charset.length]
  }

  return result
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder()
  const data = encoder.encode(plain)
  return await crypto.subtle.digest('SHA-256', data)
}

function base64URLEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''

  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }

  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '')
}
