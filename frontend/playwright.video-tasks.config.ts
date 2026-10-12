import { defineConfig } from "@playwright/test"

// Self-contained UI contracts: API routes are mocked and no real backend is used.
export default defineConfig({
  testDir: "./tests",
  testMatch: "video-tasks.spec.ts",
  fullyParallel: false,
  reporter: "line",
  use: { baseURL: "http://127.0.0.1:5178", trace: "retain-on-failure" },
  webServer: {
    command:
      "VITE_API_URL=http://127.0.0.1:8000 bun run dev --host 127.0.0.1 --port 5178",
    url: "http://127.0.0.1:5178",
    reuseExistingServer: false,
  },
})
