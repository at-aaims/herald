import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Proxy all /api/* requests to the FastAPI backend during development.
        // In production, nginx (or your load balancer) handles this routing.
        source: '/api/:path*',
        destination: `${process.env.HERALD_API_URL ?? 'http://localhost:8000'}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
