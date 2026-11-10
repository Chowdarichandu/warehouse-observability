import { test, expect } from "@playwright/test";
import type { BrowserContext } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

let adminState: Awaited<ReturnType<BrowserContext["storageState"]>>;
const screenshots = path.resolve("../output/screenshots");
test.beforeAll(async ({ browser }) => {
  mkdirSync(screenshots, { recursive: true });
  const page = await browser.newPage();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(screenshots, "login.png"),
    fullPage: true,
  });
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Pipeline overview" }),
  ).toBeVisible({ timeout: 30_000 });
  adminState = await page.context().storageState();
  await page.close();
});
test.beforeEach(async ({ context }) => {
  await context.addCookies(adminState.cookies);
});
test.afterEach(async ({ page }) => {
  await expect(
    page.getByText("Unable to load this view", { exact: true }),
  ).toHaveCount(0);
});

test("offline overview → red tenant → failed run → redacted log → successful retry", async ({
  page,
}) => {
  const external: string[] = [];
  page.on("request", (request) => {
    if (!new URL(request.url()).hostname.match(/^(localhost|127\.0\.0\.1)$/))
      external.push(request.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await expect(page.locator(".live-indicator")).toHaveText("Live");
  await page.screenshot({
    path: path.join(screenshots, "overview.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "AR Acme Retail acme_retail" }).click();
  await expect(
    page.getByRole("heading", { name: "Acme Retail", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "mysql cdc failed run", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("heading", { name: "MySQL CDC sync" }),
  ).toBeVisible();
  await expect(page.locator(".error-diagnosis")).toContainText(
    "MYSQL_BINLOG_PURGED",
  );
  await expect(
    page.getByRole("region", { name: "Redacted run log" }),
  ).toContainText("[REDACTED]");
  await expect(
    page.getByRole("region", { name: "Redacted run log" }),
  ).not.toContainText("demo-password");
  await page.screenshot({
    path: path.join(screenshots, "run-detail.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Retry run", exact: true }).click();
  await expect(page.locator(".notice")).toContainText("Simulated retry");
  await expect(page.locator(".heading-actions .status-pill")).toHaveText(
    "running",
  );
  await expect(page.locator(".heading-actions .status-pill")).toHaveText(
    "success",
    { timeout: 45_000 },
  );
  await page.goto("/tenants/acme_retail");
  await expect(page.locator(".heading-actions .status-pill")).toHaveText(
    "down",
  );
  expect(external).toEqual([]);
});

test("filters, pagination, CSV, and searchable logs", async ({ page }) => {
  await page.goto("/runs?status=failed&tenant=acme_retail&range=7d");
  await expect(
    page.getByRole("heading", { name: "Pipeline runs" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr").first()).toContainText("failed");
  await page.getByLabel("Tenant slug filter").clear();
  await expect(page.getByRole("button", { name: "Next page" })).toBeEnabled();
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page).toHaveURL(/page=2/);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("runs.csv");
  await page.getByLabel("Search tenants, logs, pages").fill("binlog");
  await page.getByLabel("Search tenants, logs, pages").press("Enter");
  await expect(page.locator(".search-results")).toContainText(
    "MYSQL_BINLOG_PURGED",
  );
});

test("errors, heatmap, recovery metrics, freshness, and schema drift", async ({
  page,
}) => {
  await page.goto("/errors?range=7d&heat_tenant=cedar_foods");
  await expect(
    page.getByRole("heading", { name: "Error groups" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect MYSQL_BINLOG_PURGED" })
    .click();
  await expect(
    page.getByRole("heading", { name: "MYSQL_BINLOG_PURGED" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Failure heatmap by hour and weekday" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Failures by stage", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Failures by tenant", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(screenshots, "errors.png"),
    fullPage: true,
  });
  await page.goto("/freshness");
  await expect(
    page.getByRole("heading", { name: "Data freshness" }),
  ).toBeVisible();
  await expect(
    page.locator(".anomaly-card").filter({ hasText: /orbit logistics/i }).first(),
  ).toBeVisible();
  await expect(page.locator(".schema-card")).toContainText("delivery_region");
  await page.screenshot({
    path: path.join(screenshots, "freshness.png"),
    fullPage: true,
  });
});

test("critical alert acknowledgment, rules, and local notification test", async ({
  page,
}) => {
  await page.goto("/alerts?state=firing");
  const alert = page
    .locator(".alert-card")
    .filter({ hasText: "CDC replication position lost" })
    .first();
  await expect(alert).toContainText("critical");
  await alert.getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByRole("status")).toContainText("acknowledged");
  await page.getByRole("button", { name: "Acknowledged" }).click();
  await expect(page.locator(".alerts-list")).toContainText(
    "CDC replication position lost",
  );
  await page
    .locator(".channel-card")
    .filter({ hasText: "slack-data-eng" })
    .getByRole("button", { name: "Send test" })
    .click();
  await expect(page.getByRole("status")).toContainText("recorded locally");
  await page.screenshot({
    path: path.join(screenshots, "alerts.png"),
    fullPage: true,
  });
});

test("four-step wizard activates Zenith Pay and updates the overview", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await page.getByLabel("Display name", { exact: true }).fill("Zenith Pay");
  await page.getByLabel("Tenant slug", { exact: true }).fill("zenith_pay");
  await page.getByLabel("Warehouse schema", { exact: true }).fill("zenith_pay");
  await page
    .getByLabel("Owner email", { exact: true })
    .fill("data@zenith.example");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByText("Connect the data sources", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByText("Binlog configuration", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(screenshots, "onboarding.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start onboarding" }).click();
  await expect(
    page.getByRole("heading", { name: "Your tenant is ready" }),
  ).toBeVisible({ timeout: 75_000 });
  await page.getByRole("link", { name: "Back to overview" }).click();
  await expect(page.locator("tbody").first()).toContainText("Zenith Pay");
});

test("platform history, admin audit, theme, TV, and mobile navigation", async ({
  page,
}) => {
  await page.goto("/platform");
  await expect(
    page.getByRole("heading", { name: "DAG import errors" }),
  ).toBeVisible();
  await expect(page.locator("table").first()).toContainText("fixed yesterday");
  await page.goto("/admin?section=audit");
  await expect(
    page.getByRole("heading", { name: "Audit trail" }),
  ).toBeVisible();
  await expect(page.locator("body")).toContainText("test channel");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: path.join(screenshots, "overview-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open TV mode" }).click();
  await expect(page.locator(".sidebar")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Exit TV mode" }).click();
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Tenants", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tenants", exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody").first()).toContainText("Acme Retail");
  await page.screenshot({
    path: path.join(screenshots, "mobile.png"),
    fullPage: true,
  });
});

test("viewer can inspect but cannot retry or administer", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/");
  await page.getByLabel("Email address").fill("viewer@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Acme Retail mysql cdc: failed" })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry run", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(
    0,
  );
  await context.close();
});
