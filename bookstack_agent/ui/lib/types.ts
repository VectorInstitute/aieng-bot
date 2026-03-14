export interface User {
  email: string
  name: string
  picture?: string
}

export interface SessionData {
  isAuthenticated: boolean
  tokens?: {
    access_token: string
    refresh_token?: string
    expires_at: number
  }
  user?: User
  state?: string
  codeVerifier?: string
}
