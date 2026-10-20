import { defineConfig } from "@playwright/test";

// Local-only mocked-API acceptance; never reuse another process or a live H5.
export default defineConfig({
	testDir: "./tests/browser",
	fullyParallel: false,
	workers: 1,
	reporter: "line",
	projects: [
		{ name: "chromium", use: { browserName: "chromium" } },
		{ name: "webkit", use: { browserName: "webkit" } },
	],
	use: {
		baseURL: "http://127.0.0.1:4182",
		trace: "retain-on-failure",
		serviceWorkers: "block",
	},
	webServer: {
		command:
			"python3 -m http.server 4182 --bind 127.0.0.1 --directory dist/vireal-pages",
		url: "http://127.0.0.1:4182",
		reuseExistingServer: false,
	},
});
