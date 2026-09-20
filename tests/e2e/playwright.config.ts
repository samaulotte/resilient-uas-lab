import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a deployed platform (default: the Compose gateway on
 * http://localhost:8080). Set RESLAB_E2E_BASE_URL to target another deployment and
 * PLAYWRIGHT_CHROMIUM_PATH to use a preinstalled Chromium binary.
 */
const baseURL = process.env.RESLAB_E2E_BASE_URL ?? "http://localhost:8080";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  outputDir: "./test-results",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { outputFolder: "./playwright-report", open: "never" }]],
  use: {
    baseURL,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
