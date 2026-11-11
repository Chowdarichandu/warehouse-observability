import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

test("capture all console screens from the running workspace", async ({
  page,
}) => {
  const directory = path.resolve("../output/screenshots");
  mkdirSync(directory, { recursive: true });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Sign in to workspace" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(directory, "login.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  const response = await page.request.get(
    "/api/runs?tenant=acme_retail&status=failed",
  );
  expect(response.ok()).toBeTruthy();
  const failed = await response.json();
  expect(failed.items.length).toBeGreaterThan(0);
  const detailResponse = await page.request.get(
    `/api/runs/${encodeURIComponent(failed.items[0].run_key)}`,
  );
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  expect(detail.previous_runs.length).toBeGreaterThan(0);
  const screens = [
    { url: "/", file: "overview.png" },
    { url: "/tenants", file: "tenants.png" },
    { url: "/tenants/acme_retail", file: "tenant-detail.png" },
    { url: "/runs?status=failed&range=7d", file: "runs.png" },
    {
      url: `/runs/${encodeURIComponent(failed.items[0].run_key)}`,
      file: "run-detail.png",
    },
    { url: "/dependencies?tenant=acme_retail", file: "dependencies.png" },
    { url: "/quality", file: "quality.png" },
    { url: "/warehouse", file: "warehouse.png" },
    { url: "/activity?tenant=acme_retail&range=1h", file: "activity.png" },
    {
      url: `/runs/${encodeURIComponent(failed.items[0].run_key)}?compare=${encodeURIComponent(detail.previous_runs[0].run_key)}`,
      file: "comparison.png",
    },
    { url: "/errors?range=7d", file: "errors.png" },
    { url: "/freshness", file: "freshness.png" },
    { url: "/alerts", file: "alerts.png" },
    { url: "/onboarding", file: "onboarding.png" },
    { url: "/platform", file: "platform.png" },
    { url: "/admin", file: "admin.png" },
    { url: "/admin?section=roles", file: "admin-roles.png" },
    { url: "/admin?section=operations", file: "admin-operations.png" },
    { url: "/admin?section=activity", file: "admin-activity.png" },
    { url: "/admin?section=audit", file: "admin-audit.png" },
    { url: "/search?q=binlog", file: "search.png" },
    { url: "/styleguide", file: "styleguide.png" },
    { url: "/?tv=1", file: "tv-mode.png" },
  ];
  const ready = async () => {
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loading" })).toHaveCount(0);
    await expect(
      page.getByText("Unable to load this view", { exact: true }),
    ).toHaveCount(0);
    const charts = page.locator(".chart-deferred");
    for (let index = 0; index < (await charts.count()); index += 1) {
      const chart = charts.nth(index);
      await chart.scrollIntoViewIfNeeded();
      await expect(chart.locator("canvas").first()).toBeAttached();
    }
    await page.evaluate(() => window.scrollTo(0, 0));
  };
  for (const screen of screens) {
    await page.goto(screen.url);
    await ready();
    await page.screenshot({
      path: path.join(directory, screen.file),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page.goto("/");
  await ready();
  await page.getByLabel("Toggle color theme").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: path.join(directory, "overview-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("Toggle color theme").click();
  await page.goto("/styleguide");
  await ready();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: path.join(directory, "styleguide-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tenants");
  await ready();
  await expect(page.locator(".health-grid-mobile")).toBeVisible();
  await expect(page.locator(".health-grid-mobile .health-card").first()).toBeVisible();
  await expect(page.locator(".health-grid-desktop")).toBeHidden();
  await page.screenshot({
    path: path.join(directory, "mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
});
