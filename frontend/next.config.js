/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  experimental: {
    optimizePackageImports: ['lucide-react', 'recharts'],
  },
  images: {
    domains: [],
  },
  // Silence the "Critical dependency" warning from chromadb being in deps tree
  webpack: (config, { isServer, nextRuntime }) => {
    // Next.js calls this hook for three compilers: client, node-server, and
    // edge (middleware). isServer is true for BOTH node-server and edge, so
    // checking isServer alone leaves the edge/middleware bundle without the
    // fallback and lets webpack inject its default Node core-module shims
    // (including a __dirname reference) into the middleware chunk. That shim
    // resolves under local Node-based emulation but throws
    // "ReferenceError: __dirname is not defined" in Vercel's real Edge
    // Runtime isolate. nextRuntime === 'edge' must be included explicitly.
    if (!isServer || nextRuntime === 'edge') {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      }
    }
    return config
  },
}

module.exports = nextConfig
