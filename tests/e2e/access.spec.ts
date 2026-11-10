import { expect, test } from "@playwright/test";
import { chooseSelectOption } from "./select";

async function login(page: import("@playwright/test").Page, role: string) {
  await page.goto("/");
  await page.getByLabel("Email address").fill(`${role}@demo.local`);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  await page.goto("/access");
  await expect(
    page.getByRole("heading", { name: "Workspace access", exact: true }),
  ).toBeVisible();
}

test("admin sees policy source and a role matrix; session revocation needs confirmation", async ({
  page,
}) => {
  await login(page, "admin");
  await expect(
    page.getByRole("heading", { name: "Workspace roles", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Workspace role permission matrix" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "User access & sessions", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Revoke sessions for viewer@demo.local",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("group", {
      name: "Confirm session revocation for viewer@demo.local",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Confirm revoke", exact: true }),
  ).toHaveCount(0);
  await chooseSelectOption(page.getByLabel("Role for viewer@demo.local"), "operator");
  await expect(
    page.getByRole("group", {
      name: "Confirm role change for viewer@demo.local",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Role for viewer@demo.local")).toContainText(
    "viewer",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../output/screenshots/access.png",
    fullPage: true,
  });
});

test("viewer can inspect their permissions without session management or privilege preview", async ({
  page,
}) => {
  await login(page, "viewer");
  await expect(
    page.getByRole("heading", { name: "User access & sessions", exact: true }),
  ).toHaveCount(0);
  await chooseSelectOption(page.getByLabel("Permission view"), "Available to me");
  await expect(page).toHaveURL(/view=available/);
  await expect(
    page
      .locator(".access-permissions")
      .getByText("View and investigate", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".access-permissions")
      .getByText("Retry pipelines", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /switch role|preview role/i }),
  ).toHaveCount(0);
  const identity = await (await page.request.get("/api/me")).json();
  const response = await page.request.patch("/api/users/0", {
    headers: { "X-CSRF-Token": identity.csrf_token },
    data: { role: "admin" },
  });
  expect(response.status()).toBe(403);
  expect((await response.json()).error.code).toBe("forbidden");
});
