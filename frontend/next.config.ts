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
      // Proxy backend API calls, but exclude NextAuth's own /api/auth/* routes
      // so they are handled by the local route handler instead of FastAPI.
      {
        source: '/api/:path((?!auth/).*)',
        destination: `${backendUrl}/api/:path`,
      },
    ]
  },
}

export default nextConfig
