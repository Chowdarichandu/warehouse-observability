import { expect, test } from "@playwright/test";

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
  await page.locator(".workspace-switch").click();
  await page.locator(".product-settings").click();
  await expect(page).toHaveURL(/\/account$/);
  await page.goto("/");
  await page.getByLabel("Text size").selectOption("large");
  await expect(page.locator("html")).toHaveCSS("zoom", "1.12");
  await page.reload();
  await expect(page.getByLabel("Text size")).toHaveValue("large");
  await page.getByLabel("Text size").selectOption("standard");
  await page.getByLabel("Search errors and logs").fill("acme");
  await page.getByRole("button", { name: "Submit global search" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenants", exact: true }),
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
