/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite serves the UI with HMR and proxies the data plane to the Python server
// (JSON API + the /img snapshots + the /api/events SSE stream). Prod: `pnpm build`
// emits into the Python package's web/dist, which app.py serves from the checkout.
const BACKEND = "http://127.0.0.1:47824";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 47825,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/img": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: "../src/defringe_ai/web/dist",
    emptyOutDir: true,
  },
  // Vitest: fast jsdom unit tests over the pure logic in state.ts (the module the
  // frontend.md rule funnels all server I/O through). Coverage is gated so the UI's
  // data plane stays as tested as the Python side.
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/state.ts"],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
});
