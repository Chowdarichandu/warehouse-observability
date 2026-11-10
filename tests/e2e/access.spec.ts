import { expect, test } from "@playwright/test";
import path from "node:path";
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
  await chooseSelectOption(
    page.getByLabel("Role for viewer@demo.local"),
    "operator",
  );
  await expect(
    page.getByRole("group", {
      name: "Confirm role change for viewer@demo.local",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Role for viewer@demo.local")).toContainText(
    /viewer/i,
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
  await chooseSelectOption(
    page.getByLabel("Permission view"),
    "Available to me",
  );
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

test("admin can onboard and remove a user with one-time credentials", async ({
  page,
  context,
}) => {
  await login(page, "admin");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/admin");
  const email = `demo-e2e-${Date.now()}@example.com`;
  await page.getByRole("button", { name: /Add user/ }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Display name", { exact: true }).fill("E2E Demo User");
  await page.getByRole("button", { name: /Create user/ }).click();

  const credentials = page.getByRole("dialog", { name: "Temporary password" });
  await expect(credentials).toContainText(email);
  await expect(credentials.locator(".temp-password")).toHaveText(
    "••••••••••••",
  );
  await credentials.getByRole("button", { name: "Copy password" }).click();
  await expect(page.getByRole("status")).toContainText("password copied");
  const copiedPassword = await page.evaluate(async () => {
    const password = await navigator.clipboard.readText();
    await navigator.clipboard.writeText("");
    return password;
  });
  expect(copiedPassword.length).toBeGreaterThan(12);
  await credentials.getByRole("button", { name: "Reveal password" }).click();
  await expect(credentials.locator(".temp-password")).toHaveText(
    copiedPassword,
  );
  await credentials.getByRole("button", { name: "Hide password" }).click();
  await credentials.getByRole("button", { name: "Done" }).click();

  const userRow = page.locator("tr").filter({ hasText: email });
  await expect(userRow).toBeVisible();
  await page.locator(".profile-main").click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(copiedPassword);
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();

  await page.goto("/account");
  const changedPassword = `e2e-updated-passphrase-${Date.now()}`;
  await page.getByLabel("Current password").fill(copiedPassword);
  await page.getByLabel("New password").fill(changedPassword);
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("Password updated");

  await page.locator(".profile-main").click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(changedPassword);
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();

  await page.locator(".profile-main").click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await page.goto("/admin");
  const createdUser = page.locator("tr").filter({ hasText: email });
  await expect(createdUser).toBeVisible();
  await createdUser.getByRole("button", { name: "Remove" }).click();
  const removeDialog = page.getByRole("dialog", { name: "Remove user" });
  await expect(removeDialog).toContainText(email);
  await removeDialog.getByRole("button", { name: "Remove user" }).click();
  await expect(createdUser).toHaveCount(0);
});

test("role creation stays readable and usable on desktop and mobile", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin?section=roles");
  await expect(
    page.getByRole("heading", { name: "Roles & permissions", exact: true }),
  ).toBeVisible();

  const nameField = page.getByLabel("Role name", { exact: true });
  const nameBounds = await nameField.boundingBox();
  const descriptionBounds = await page
    .getByPlaceholder("e.g. On-call support engineers")
    .boundingBox();
  const firstRoleCard = await page.locator(".role-card").nth(0).boundingBox();
  const secondRoleCard = await page.locator(".role-card").nth(1).boundingBox();
  const roleList = await page.locator(".roles-list").boundingBox();
  const roleForm = await page.locator(".role-form").boundingBox();
  expect(nameBounds?.width).toBeGreaterThan(400);
  expect(descriptionBounds?.width).toBeGreaterThan(nameBounds?.width ?? 0);
  expect(
    (secondRoleCard?.x ?? 0) -
      ((firstRoleCard?.x ?? 0) + (firstRoleCard?.width ?? 0)),
  ).toBeGreaterThanOrEqual(14);
  expect(
    (roleForm?.y ?? 0) - ((roleList?.y ?? 0) + (roleList?.height ?? 0)),
  ).toBeGreaterThanOrEqual(24);
  await page.screenshot({
    path: path.resolve("../output/screenshots/admin-roles.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(nameField).toBeVisible();
  const mobileBounds = await nameField.boundingBox();
  expect(mobileBounds?.width).toBeGreaterThan(250);
  expect(
    (mobileBounds?.x ?? 0) + (mobileBounds?.width ?? 0),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: path.resolve("../output/screenshots/admin-roles-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  const roleName = `support_e2e_${Date.now()}`;
  await nameField.fill(roleName);
  await page.getByRole("button", { name: "Create role", exact: true }).click();
  const roleCard = page.locator(".role-card").filter({ hasText: roleName });
  await expect(roleCard).toBeVisible();
  await expect(roleCard).toContainText("Trigger & retry pipelines");
  await roleCard
    .getByRole("button", { name: `Delete role ${roleName}` })
    .click();
  await expect(roleCard).toHaveCount(0);
});
