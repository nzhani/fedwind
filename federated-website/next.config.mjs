/** @type {import('next').NextConfig} */

// The browser calls the API on the website's own address (/api/...); the web server forwards it.
// One address works for localhost and for a public tunnel, and the session cookie stays first-party.
// API_INTERNAL_URL: where this server reaches the API (Docker: http://api:8000, set at build time).
const API_INTERNAL_URL = (process.env.API_INTERNAL_URL || "http://localhost:8001").replace(/\/$/, "")

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    proxyTimeout: 120_000, // forecasts and run uploads can take longer than the 30 s default
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` },
      { source: "/site-api/:path*", destination: `${API_INTERNAL_URL}/site-api/:path*` },
    ]
  },
}

export default nextConfig
