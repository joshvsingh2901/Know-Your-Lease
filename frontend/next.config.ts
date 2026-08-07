import type { NextConfig } from "next";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

if (process.env.VERCEL_ENV === "production" && !apiBaseUrl) {
  throw new Error("NEXT_PUBLIC_API_BASE_URL is required for a Vercel production build.");
}

if (apiBaseUrl) {
  let parsedApiBaseUrl: URL;
  try {
    parsedApiBaseUrl = new URL(apiBaseUrl);
  } catch {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) origin.");
  }
  if (
    !["http:", "https:"].includes(parsedApiBaseUrl.protocol) ||
    parsedApiBaseUrl.username ||
    parsedApiBaseUrl.password ||
    parsedApiBaseUrl.pathname !== "/" ||
    parsedApiBaseUrl.search ||
    parsedApiBaseUrl.hash
  ) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be an HTTP(S) origin without a path.");
  }
  if (process.env.VERCEL_ENV === "production" && parsedApiBaseUrl.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must use HTTPS in Vercel production.");
  }
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
