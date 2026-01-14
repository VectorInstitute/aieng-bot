import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  basePath: '/aieng-bot',
  output: 'standalone',

  // Disable experimental features that may cause issues
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },

  // Image optimization
  images: {
    unoptimized: true,
  },

  // Environment variables available to the browser
  env: {
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3001',
    NEXT_PUBLIC_GOOGLE_CLIENT_ID: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
  },
}

export default nextConfig
