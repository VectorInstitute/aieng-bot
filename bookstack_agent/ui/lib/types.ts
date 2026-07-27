export interface User {
  email: string
  name: string
  picture?: string
}

export interface SessionData {
  isAuthenticated: boolean
  user?: User
  state?: string
  codeVerifier?: string
}
