import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, role: "admin" | "viewer") {
  await page.goto("/");
  await page.getByLabel("Email address").fill(`${role}@demo.local`);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
}

test("search stays in view on mobile and opens tenant, page, and error results", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "admin");
  const search = page.getByLabel("Search tenants, logs, pages");
  const suggestions = page.getByRole("region", { name: "Search suggestions" });
  for (const theme of ["light", "dark"]) {
    if ((await page.locator("html").getAttribute("data-theme")) !== theme) {
      await page.getByLabel("Toggle color theme").click();
    }
    await search.fill("acme");
    await expect(
      suggestions.getByRole("button", { name: /Acme Retail/ }),
    ).toBeVisible();
    const bounds = await suggestions.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
    const audit = await new AxeBuilder({ page })
      .include("#search-suggestions")
      .analyze();
    expect(audit.violations).toEqual([]);
    await search.press("ArrowDown");
    await expect(
      suggestions.getByRole("button", { name: /Acme Retail/ }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(suggestions).toBeHidden();
    await expect(search).toBeFocused();
  }
  await search.fill("acme retail");
  await suggestions.getByRole("button", { name: /Acme Retail/ }).click();
  await expect(page).toHaveURL(/\/tenants\/acme_retail$/);

  await search.fill("dag");
  await suggestions.getByRole("button", { name: "Orchestration" }).click();
  await expect(page).toHaveURL(/\/pipelines$/);

  await search.fill("mysql_binlog_purged");
  await page.getByRole("button", { name: "Submit global search" }).click();
  const hit = page.locator(".search-results").getByRole("link").first();
  await expect(hit).toContainText("MYSQL_BINLOG_PURGED");
  await hit.click();
  await expect(page).toHaveURL(/\/runs\/.+\?focus=log$/);
  await expect(
    page.getByRole("region", { name: "Redacted run log" }),
  ).toBeVisible();
});

test("search destinations match the signed-in user's navigation", async ({
  page,
}) => {
  await signIn(page, "viewer");
  const search = page.getByLabel("Search tenants, logs, pages");
  await search.fill("administration");
  const suggestions = page.getByRole("region", { name: "Search suggestions" });
  await expect(suggestions).toBeVisible();
  await expect(
    suggestions.getByRole("button", { name: "Administration", exact: true }),
  ).toHaveCount(0);
  await search.press("Enter");
  await expect(page.getByText("No matching tenants.")).toBeVisible();
  await expect(
    page.getByText("No matching errors or logs.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator("main a[href='/admin']")).toHaveCount(0);
});
