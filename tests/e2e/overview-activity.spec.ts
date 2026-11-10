import { expect, test } from "@playwright/test";
import { chooseSelectIndex, chooseSelectOption, expectSelectOptionCount, expectSelectOptionNamed } from "./select";

test("tenant selection updates run choices and opens the selected log", async ({
  page,
}) => {
  await page.route("**/api/runs?*", async (route) => {
    const tenant = new URL(route.request().url()).searchParams.get("tenant");
    if (tenant !== "acme_retail" && tenant !== "orbit_logistics") {
      await route.continue();
      return;
    }
    await route.fulfill({
      json: {
        items: [
          {
            run_key: `${tenant}-run`,
            source_type: "mysql",
            load_type: "initial",
            status: "success",
            started_at: "2026-01-01T00:00:00Z",
            collected_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 200,
      },
    });
  });
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();

  const tenant = page.getByLabel("Run activity tenant");
  const log = page.getByLabel("Open run log");
  await chooseSelectOption(tenant, "Acme Retail");
  await expectSelectOptionCount(log, 2);
  const orbitRuns = page.waitForResponse(
    (response) =>
      response.url().includes("/api/runs") &&
      response.url().includes("tenant=orbit_logistics"),
  );
  await chooseSelectOption(tenant, "Orbit Logistics");
  await orbitRuns;
  await expectSelectOptionCount(log, 2);
  await chooseSelectIndex(log, 1);
  await expect(page).toHaveURL(/\/runs\/orbit_logistics-run\?focus=log$/);
});
