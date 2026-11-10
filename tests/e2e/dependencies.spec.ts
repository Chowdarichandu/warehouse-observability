import { test, expect } from "@playwright/test";
import { chooseSelectOption } from "./select";

test("dependency map explains evidence and retains tenant and node selections in URL", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("viewer@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  await page.goto("/dependencies?tenant=acme_retail");
  await expect(
    page.getByRole("heading", { name: "Pipeline dependencies", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "source: MySQL", exact: true })
    .click();
  await expect(page).toHaveURL(/node=source/);
  await expect(
    page.getByRole("heading", {
      name: "Potential downstream impact",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Configured source mapping", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/do not establish SQL or record-level lineage/),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "source: MySQL", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await chooseSelectOption(
    page.getByLabel("Tenant", { exact: true }),
    "Orbit Logistics",
  );
  await expect(page).toHaveURL(/tenant=orbit_logistics/);
  await expect(
    page.getByRole("button", {
      name: "warehouse: orbit_logistics",
      exact: true,
    }),
  ).toBeVisible();
});
