import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In dev the API runs separately; in production nginx proxies /api.
    proxy: { "/api": "http://localhost:8000" },
  },
  test: { environment: "node" },
});
