/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server build for slim Docker images (optional —
  // ignored by Vercel, which is the primary frontend target).
  output: "standalone",
  // Allow the frontend to be deployed independently of the API.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
};

export default nextConfig;
