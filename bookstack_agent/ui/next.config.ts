import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  basePath: '/aieng-bot',
  output: 'standalone',
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3001',
  },
}

export default nextConfig
