import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

declare const process: { env: Record<string, string | undefined> };

// The API runs on :8000 in dev; the PWA proxies /api there so the same-origin
// fetch path works in both dev and a single-origin production deployment.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      // Don't let the SPA navigation fallback swallow API calls when the API is
      // served under /api on the same origin in production.
      workbox: { navigateFallbackDenylist: [/^\/api/] },
      manifest: {
        name: "Clinic Cash Register",
        short_name: "Cash Register",
        description: "Partnership cash-management for a small clinic",
        theme_color: "#ffffff",
        background_color: "#f5f5f7",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
