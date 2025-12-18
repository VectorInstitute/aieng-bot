import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Maintenance Analytics - Vector Institute',
  description: 'Monitor and analyze automated PR maintenance across Vector Institute repositories',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
