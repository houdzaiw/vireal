import { defineConfig } from "@playwright/test"
import base from "./playwright.config"

// Never reuse another checkout's server when testing an uncommitted patch.
export default defineConfig({
  ...base,
  use: { ...base.use, baseURL: "http://127.0.0.1:4189" },
  webServer: {
    command: "python3 -m http.server 4189 --bind 127.0.0.1 --directory dist/vireal-pages",
    url: "http://127.0.0.1:4189",
    reuseExistingServer: false,
  },
})
