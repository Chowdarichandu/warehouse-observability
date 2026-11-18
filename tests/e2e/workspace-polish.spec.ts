import { expect, test } from "@playwright/test";
import { chooseSelectOption } from "./select";

test("search, navigation, typography, and administration work together", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  const collapse = page.getByRole("button", { name: "Collapse sidebar" });
  await expect(collapse).toHaveCSS("width", "32px");
  await collapse.click();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(collapse).toBeVisible();
  await page.locator(".workspace-switch").click();
  await expect(page.locator("#workspace-product-menu")).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
  const overviewLink = page.getByRole("link", {
    name: "Overview",
    exact: true,
  });
  const textSize = () =>
    overviewLink.evaluate((link) =>
      parseFloat(getComputedStyle(link).fontSize),
    );
  const standardSize = await textSize();
  await chooseSelectOption(page.getByLabel("Text size"), "Large");
  await expect.poll(textSize).toBeGreaterThan(standardSize);
  await page.reload();
  await expect(page.getByLabel("Text size")).toContainText("Large");
  await expect.poll(textSize).toBeGreaterThan(standardSize);
  await chooseSelectOption(page.getByLabel("Text size"), "Standard");
  await page.goto("/");
  await page.getByLabel("Search tenants, logs, pages").fill("acme");
  await page.getByRole("button", { name: "Submit global search" }).click();
  await expect(
    page.getByRole("heading", { name: "Search", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".search-section")
      .filter({ has: page.getByRole("heading", { name: "Tenants" }) })
      .getByRole("link", { name: /Acme Retail/ }),
  ).toBeVisible();
  await page.getByLabel("Search query").fill("binlog");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".search-results")).toContainText(
    "MYSQL_BINLOG_PURGED",
  );
  await page.goto("/workspace/pipelines");
  await expect(page).toHaveURL(/\/pipelines$/);
  await expect(
    page.getByRole("heading", { name: "Pipeline orchestration" }),
  ).toBeVisible();
  await expect(page.getByLabel("Analytics DAGs")).toContainText(
    "Analytics marts build",
  );
  await page.locator(".profile-main").click();
  await expect(
    page.getByRole("link", { name: "Account settings", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Account settings", exact: true })
    .click();
  await expect(page).toHaveURL(/\/account$/);
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Users & roles" }),
  ).toBeVisible();
  const viewerRow = page.locator("tr").filter({ hasText: "viewer@demo.local" });
  await viewerRow.getByRole("button", { name: "Permissions" }).click();
  const permissionsDialog = page.getByRole("dialog", {
    name: "User permissions",
  });
  await expect(permissionsDialog).toContainText("viewer@demo.local");
  await expect(
    permissionsDialog.getByText(
      "Permissions from a higher tier can't be added here",
      { exact: false },
    ),
  ).toBeVisible();
  await permissionsDialog.getByRole("button", { name: "Close" }).click();
  await page.route("**/api/v1/users/*/reset-password", async (route) => {
    await route.fulfill({
      json: {
        message: "Password reset",
        temporary_password: "Demo-Temporary-Only-42",
        simulated: true,
      },
    });
  });
  await viewerRow.getByRole("button", { name: "Reset" }).click();
  await page
    .getByRole("dialog", { name: "Reset password" })
    .getByRole("button", { name: "Reset password" })
    .click();
  const temporaryDialog = page.getByRole("dialog", {
    name: "Temporary password",
  });
  await expect(temporaryDialog.locator(".temp-password")).toHaveText(
    "••••••••••••",
  );
  await expect(temporaryDialog).not.toContainText("Demo-Temporary-Only-42");
  await temporaryDialog
    .getByRole("button", { name: "Reveal password" })
    .click();
  await expect(temporaryDialog.locator(".temp-password")).toHaveText(
    "Demo-Temporary-Only-42",
  );
  await temporaryDialog.getByRole("button", { name: "Done" }).click();
  await expect(page.locator("body")).not.toContainText(
    "Demo-Temporary-Only-42",
  );
  await page.getByRole("button", { name: "Audit trail", exact: true }).click();
  await expect(page).toHaveURL(/section=audit/);
  await expect(
    page.getByRole("heading", { name: "Audit trail" }),
  ).toBeVisible();
  await page.goto("/");
  await page
    .locator("tr.health-row")
    .filter({ hasText: "Acme Retail" })
    .locator("td")
    .nth(1)
    .click();
  await expect(page).toHaveURL(/\/tenants\/acme_retail/);
  const workflow = page.locator(".panel").filter({
    has: page.getByRole("heading", { name: "Workflows", exact: true }),
  });
  await expect(
    workflow.getByText("Managed by onboarding").first(),
  ).toBeVisible();
  await expect(workflow.getByText("Managed by schedule").first()).toBeVisible();
  await expect(
    workflow.locator(".wf-card:not(.wf-analytics) button"),
  ).toHaveCount(0);
});

test("mobile filters remain aligned and dropdowns stay attached with Large text", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("obs-text-size", "large"),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  await page.goto("/tenants");

  const filter = page.getByRole("button", { name: "Filter by health" });
  const input = page.locator(".filter-bar .search-field");
  await expect(filter).toHaveCSS("height", "36px");
  await expect(input).toHaveCSS("height", "36px");
  const ring = await filter.evaluate(
    (item) => getComputedStyle(item).borderColor,
  );
  await expect(input).toHaveCSS("border-top-color", ring);
  await filter.press("Enter");
  const menu = page.getByRole("listbox", { name: "Filter by health" });
  await expect(menu).toBeVisible();
  const trigger = (await filter.boundingBox())!;
  const popup = (await menu.boundingBox())!;
  const gap = Math.min(
    Math.abs(popup.y - trigger.y - trigger.height),
    Math.abs(trigger.y - popup.y - popup.height),
  );
  expect(gap).toBeLessThanOrEqual(8);
  expect(popup.x).toBeGreaterThanOrEqual(0);
  expect(popup.x + popup.width).toBeLessThanOrEqual(390);
  await menu.getByRole("option", { name: "down", exact: true }).click();
  await expect(page).toHaveURL(/health=down/);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);

  await page.goto("/access");
  await expect(
    page.getByRole("heading", { name: "User access & sessions" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
