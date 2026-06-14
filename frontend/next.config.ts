import type { NextConfig } from 'next'

// In Docker the Next.js server calls the backend container directly.
// Locally (outside Docker) this falls back to localhost:8000.
const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000'

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
