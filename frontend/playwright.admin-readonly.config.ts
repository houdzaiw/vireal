import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./tests",
  testMatch: "admin-wallet-readonly.spec.ts",
  fullyParallel: false,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:5181",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      "VITE_API_URL=http://127.0.0.1:8000 bun run dev --host 127.0.0.1 --port 5181 --strictPort",
    url: "http://127.0.0.1:5181",
    reuseExistingServer: false,
  },
})
