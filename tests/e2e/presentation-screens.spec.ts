import { expect, test } from "@playwright/test";
import { chooseSelectOption } from "./select";
import path from "node:path";

test("capture the redesigned orchestration and account screens", async ({
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
  for (const screen of [
    {
      url: "/pipelines",
      heading: "Pipeline orchestration",
      file: "orchestration.png",
    },
    { url: "/access", heading: "Workspace access", file: "access.png" },
    { url: "/account", heading: "Account settings", file: "account.png" },
  ]) {
    await page.goto(screen.url);
    await expect(
      page.getByRole("heading", { name: screen.heading, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Unable to load this view", { exact: true }),
    ).toHaveCount(0);
    await page.screenshot({
      path: path.resolve("../output/screenshots", screen.file),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page.goto("/");
  await chooseSelectOption(page.getByLabel("Run activity tenant"), "Acme Retail");
  const run = page.getByLabel("Open run log");
  await run.click();
  await expect(page.getByRole("option")).not.toHaveCount(1);
  await page.getByRole("option").nth(1).click();
  await expect(page).toHaveURL(/focus=log/);
  await expect(page.locator("#run-log")).toBeInViewport();
});
