/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    instrumentationHook: true,
    // undici는 서버에서 런타임 require로 쓴다(fetchBackend의 dispatcher Agent).
    // webpack이 번들하려 하면 undici 내부 문법에서 파싱 실패하므로 외부 패키지로 둔다.
    serverComponentsExternalPackages: ['undici'],
  },
}

module.exports = nextConfig


