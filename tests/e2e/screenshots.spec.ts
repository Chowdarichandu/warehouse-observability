import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

test("capture every console screen across light/dark desktop and mobile themes", async ({
  page,
}) => {
  test.setTimeout(420_000);
  const capturedAt = new Date();
  await page.clock.setFixedTime(capturedAt);
  const directory = path.resolve("../docs/screenshots");
  mkdirSync(directory, { recursive: true });

  const viewports = [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ];
  const themes = ["light", "dark"] as const;
  for (const viewport of viewports) {
    for (const theme of themes) {
      const loginPage = await page.context().newPage();
      await loginPage.clock.setFixedTime(capturedAt);
      await loginPage.setViewportSize(viewport);
      await loginPage.addInitScript(
        (savedTheme) => localStorage.setItem("obs-theme", savedTheme),
        theme,
      );
      await loginPage.goto("/");
      await expect(
        loginPage.getByRole("heading", { name: "Sign in", exact: true }),
      ).toBeVisible();
      await loginPage.screenshot({
        path: path.join(directory, `login-${theme}-${viewport.width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await loginPage.close();
    }
  }

  await page.setViewportSize(viewports[0]);
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Sign in to workspace" }),
  ).toBeVisible();
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();

  const response = await page.request.get(
    "/api/v1/runs?tenant=acme_retail&status=failed",
  );
  expect(response.ok()).toBeTruthy();
  const failed = await response.json();
  expect(failed.items.length).toBeGreaterThan(0);
  const detailResponse = await page.request.get(
    `/api/v1/runs/${encodeURIComponent(failed.items[0].run_key)}`,
  );
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  expect(detail.previous_runs.length).toBeGreaterThan(0);

  const screens = [
    { slug: "overview", url: "/" },
    { slug: "tenants", url: "/tenants" },
    { slug: "tenant-detail", url: "/tenants/acme_retail" },
    { slug: "orchestration", url: "/pipelines" },
    { slug: "runs", url: "/runs?status=failed&range=7d" },
    {
      slug: "run-detail",
      url: `/runs/${encodeURIComponent(failed.items[0].run_key)}`,
    },
    { slug: "dependencies", url: "/dependencies?tenant=acme_retail" },
    { slug: "quality", url: "/quality" },
    { slug: "warehouse", url: "/warehouse" },
    { slug: "activity", url: "/activity?tenant=acme_retail&range=1h" },
    {
      slug: "comparison",
      url: `/runs/${encodeURIComponent(failed.items[0].run_key)}?compare=${encodeURIComponent(detail.previous_runs[0].run_key)}`,
    },
    { slug: "errors", url: "/errors?range=7d" },
    { slug: "freshness", url: "/freshness" },
    { slug: "alerts", url: "/alerts" },
    { slug: "incidents", url: "/incidents" },
    { slug: "onboarding", url: "/onboarding" },
    { slug: "platform", url: "/platform" },
    { slug: "access", url: "/access" },
    { slug: "account", url: "/account" },
    { slug: "dev-mailbox", url: "/dev/mailbox" },
    { slug: "admin", url: "/admin" },
    { slug: "admin-roles", url: "/admin?section=roles" },
    { slug: "admin-operations", url: "/admin?section=operations" },
    { slug: "admin-activity", url: "/admin?section=activity" },
    { slug: "admin-audit", url: "/admin?section=audit" },
    { slug: "search", url: "/search?q=binlog" },
    { slug: "styleguide", url: "/styleguide" },
    { slug: "tv-mode", url: "/?tv=1" },
  ];

  const ready = async (url: string) => {
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (new URL(url, page.url()).pathname !== "/styleguide") {
      await expect(page.getByRole("status", { name: "Loading" })).toHaveCount(
        0,
      );
      await expect(
        page.getByText("Unable to load this view", { exact: true }),
      ).toHaveCount(0);
    }
    const charts = page.locator(".chart-deferred");
    for (let index = 0; index < (await charts.count()); index += 1) {
      const chart = charts.nth(index);
      await chart.scrollIntoViewIfNeeded();
      await expect(chart.locator("canvas").first()).toBeAttached();
    }
    await page.evaluate(() => window.scrollTo(0, 0));
  };

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    for (const theme of themes) {
      await page.goto("/");
      await ready("/");
      const currentTheme = await page
        .locator("html")
        .getAttribute("data-theme");
      if (currentTheme !== theme) {
        await page.getByLabel("Toggle color theme").click();
      }
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      for (const screen of screens) {
        await page.goto(screen.url);
        await ready(screen.url);
        if (screen.slug === "tenants" && viewport.width === 390) {
          await expect(page.locator(".health-grid-mobile")).toBeVisible();
          await expect(page.locator(".health-grid-desktop")).toBeHidden();
        }
        await page.screenshot({
          path: path.join(
            directory,
            `${screen.slug}-${theme}-${viewport.width}.png`,
          ),
          fullPage: true,
          animations: "disabled",
        });
      }
    }
  }
});
