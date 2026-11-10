import { expect, test } from "@playwright/test";
import { chooseSelectIndex, chooseSelectOption, expectSelectOptionCount, expectSelectOptionNamed } from "./select";

test("personal views survive reload and run investigation compares evidence", async ({
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
  await page.goto("/runs?tenant=acme_retail&status=failed&range=7d");
  const name = `CDC investigation ${Date.now()}`;
  await page.getByLabel("New saved view name").fill(name);
  await page.getByRole("button", { name: "Save view", exact: true }).click();
  await expectSelectOptionNamed(
    page.getByLabel("Saved investigation views"),
    name,
    1,
  );
  await page.reload();
  await chooseSelectOption(page.getByLabel("All statuses"), "success");
  await chooseSelectOption(page.getByLabel("Saved investigation views"), name);
  await expect(page.getByLabel("All statuses")).toContainText("failed");
  await expect(page).toHaveURL(/status=failed/);
  await page.getByRole("button", { name: "Delete selected view" }).click();
  await expectSelectOptionNamed(
    page.getByLabel("Saved investigation views"),
    name,
    0,
  );
  await page
    .getByRole("link", { name: "Open failed run for acme_retail" })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Compare runs", exact: true }),
  ).toBeVisible();
  const baseline = page.getByLabel("Comparison baseline");
  await baseline.click();
  await expect(page.getByRole("option")).not.toHaveCount(1);
  await page.getByRole("option").nth(1).click();
  await expect(
    page.getByRole("table", { name: "Run comparison" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/compare=/);
  await page.getByLabel("Search within log").fill("ERROR");
  await expect(
    page.getByRole("button", { name: "Next log match" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Next log match" }).click();
  await page.getByLabel("Matching lines only").click();
  await expect(page.getByLabel("Matching lines only")).toBeChecked();
  await expect(page.locator(".log-viewer li").first()).toContainText(/ERROR/i);
  await expect(
    page.getByRole("heading", { name: "Event timeline", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".investigation-timeline li").first(),
  ).toBeVisible();
  await page.goto("/activity?tenant=acme_retail&range=7d");
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Unable to load this view", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.locator(".investigation-timeline li").first(),
  ).toBeVisible();
});
