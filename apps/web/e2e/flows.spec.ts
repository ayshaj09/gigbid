import { expect, Page, test } from "@playwright/test";

const API = "http://localhost:8100";

async function signUpAndOnboard(page: Page) {
  const email = `u${Date.now()}${Math.floor(Math.random() * 1000)}@example.com`;
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
}

async function analyse(page: Page, jobId: string) {
  await page.getByLabel("Job id").fill(jobId);
  await page.getByRole("button", { name: "Analyse job" }).click();
  await expect(page.getByTestId("run-progress").getByText(/Finished/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: /./ }).filter({ hasText: /Celery|invoices|RAG|churn|ETL/ }).first().click();
  await expect(page.getByTestId("proposal-studio")).toBeVisible();
}

test("onboarding lands on the inbox", async ({ page }) => {
  await signUpAndOnboard(page);
  await expect(page.getByText(/No jobs yet/)).toBeVisible();
});

test("approve: evidence on hover, then submit; approval survives a refresh", async ({ page }) => {
  await signUpAndOnboard(page);
  await analyse(page, "J-104");
  await page.reload();                                         // pending approval survives refresh
  await expect(page.getByTestId("proposal-studio")).toBeVisible();
  const claim = page.locator(".claim").first();
  await claim.hover();
  await expect(claim.getByRole("tooltip")).toContainText("Celery");
  await expect(page.getByTestId("proposal-studio").getByText(/10 Connects/).first()).toBeVisible();   // dry-run cost shown before approval
  await page.getByRole("button", { name: "Approve and submit" }).click();
  await expect(page.getByText(/Submitted as P-/)).toBeVisible({ timeout: 30_000 });
});

test("reject with a reason shows up in analytics", async ({ page }) => {
  await signUpAndOnboard(page);
  await analyse(page, "J-106");
  await page.getByRole("button", { name: "Reject" }).click();
  await page.getByLabel("Reason for rejecting").fill("not my niche");
  await page.getByRole("button", { name: "Confirm reject" }).click();
  await expect(page.getByText("rejected").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByText("not my niche")).toBeVisible();
});

test("edit: compliance re-checks the edit before it is sent", async ({ page }) => {
  await signUpAndOnboard(page);
  await analyse(page, "J-104");
  await page.getByRole("button", { name: "Edit" }).click();
  const box = page.getByLabel("Edit proposal");
  await box.fill((await box.inputValue()) + " Email me at me@example.com to move faster.");
  await page.getByRole("button", { name: "Save edit and approve" }).click();
  await expect(page.getByText(/Compliance changed this text/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("annotated-letter")).not.toContainText("example.com");
  await page.getByRole("button", { name: "Approve and submit" }).click();
  await expect(page.getByText(/Submitted as P-/)).toBeVisible({ timeout: 30_000 });
});

test("marketplace outage: banner, work queued, then recovers", async ({ page, request }) => {
  await signUpAndOnboard(page);
  await request.post(`${API}/internal/dev/marketplace?down=true`, { headers: { "X-Internal-Token": "e2e-internal" } });
  await page.getByLabel("Job id").fill("J-104");
  await page.getByRole("button", { name: "Analyse job" }).click();
  await expect(page.getByTestId("run-progress").getByText(/waiting_for_marketplace/)).toBeVisible({ timeout: 40_000 });
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toBeVisible();
  await request.post(`${API}/internal/dev/marketplace?down=false`, { headers: { "X-Internal-Token": "e2e-internal" } });
  await page.reload();   // banner state is polled; the stand-in is back up now
  await expect(page.getByTestId("degraded-banner")).toHaveCount(0, { timeout: 20_000 });
  // what the worker does every 2 minutes:
  const r = await request.post(`${API}/internal/retry_waiting`, { headers: { "X-Internal-Token": "e2e-internal" } });
  expect((await r.json()).resumed).toBe(1);
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toHaveCount(0);
  await expect(page.locator("tbody .badge", { hasText: "awaiting approval" })).toBeVisible();
});
