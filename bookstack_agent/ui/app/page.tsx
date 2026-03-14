import { redirect } from 'next/navigation'
import { isAuthenticated, getCurrentUser } from '@/lib/session'
import ChatPage from './components/chat-page'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    redirect('/login')
  }
  const user = await getCurrentUser()
  return <ChatPage user={user} />
}
