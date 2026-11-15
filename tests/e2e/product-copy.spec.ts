import { expect, test } from "@playwright/test";

test("sign-in uses the Pravah product-first layout", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.locator(".login-brand")).toContainText("Pravah");
  await expect(page.locator(".demo-label")).toBeVisible();
  await expect(page).toHaveTitle("Sign in · Pravah");
  await expect(page.getByText("WAREHOUSE OBSERVABILITY", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Pipeline operations.", { exact: true })).toHaveCount(0);
});

test("planned modules are visible but have no dead-end action", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();

  await expect(page.getByRole("heading", { name: "Tenant health", exact: true })).toBeVisible();
  await expect(page.locator(".breadcrumb").getByRole("link", { name: "Pravah" })).toBeVisible();
  await expect(page).toHaveTitle(/Overview · Pravah$/);

  await page.getByTitle("Product navigation").click();
  const plannedModule = page.getByLabel("HRMS, planned; no screens available");
  await expect(plannedModule).toBeVisible();
  await expect(plannedModule.locator("a, button, [role=button]")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /HRMS/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /HRMS/ })).toHaveCount(0);

  await plannedModule.click();
  await expect(plannedModule).toBeVisible();
  await expect(page.locator(".toast")).toHaveCount(0);
});
