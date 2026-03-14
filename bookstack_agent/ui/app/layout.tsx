import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'BookStack QA — Vector Institute',
  description: 'Ask questions about Vector Institute internal documentation',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  )
}
