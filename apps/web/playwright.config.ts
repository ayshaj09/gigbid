import { defineConfig } from "@playwright/test";

// Starts the API (offline models, fixture marketplace, throwaway DBs) and the built web app.
const tmp = process.env.E2E_TMP ?? "/tmp/gigbid-e2e";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3100",
    channel: process.env.PW_CHANNEL ?? undefined, // e.g. "chrome" to use an installed Google Chrome
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `rm -rf ${tmp} && mkdir -p ${tmp} && cd ../.. && APP_DB=${tmp}/app.sqlite GIGBID_SQLITE=${tmp}/ckpt.sqlite GIGBID_DATA_DIR=${tmp} MODEL_PROFILE=offline GIGSIM_BASE_URL=fixture:// MARKETPLACE_RPM=6000 DATABASE_URL= INTERNAL_TOKEN=e2e-internal WEB_ORIGINS=http://localhost:3100 python -m uvicorn apps.api.main:app --port 8100`,
      url: "http://localhost:8100/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "NEXT_PUBLIC_API_URL=http://localhost:8100 npx next build && NEXT_PUBLIC_API_URL=http://localhost:8100 npx next start -p 3100",
      url: "http://localhost:3100/login",
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
