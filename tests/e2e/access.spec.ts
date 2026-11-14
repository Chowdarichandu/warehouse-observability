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
    path: "../docs/screenshots/access.png",
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
    path: path.resolve("../docs/screenshots/admin-roles.png"),
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
    path: path.resolve("../docs/screenshots/admin-roles-mobile.png"),
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

test("metrics-only role assignment limits the UI and API to aggregate metrics", async ({
  page,
}) => {
  await login(page, "admin");
  const roleName = `metrics_view_${Date.now()}`;
  const viewerEmail = "viewer@demo.local";
  let roleCreated = false;
  let viewerId: number | undefined;
  let viewerContext: import("@playwright/test").BrowserContext | undefined;
  const adminIdentity = await (await page.request.get("/api/me")).json();

  try {
    await page.goto("/admin?section=roles");
    await page.getByLabel("Role name", { exact: true }).fill(roleName);
    await chooseSelectOption(
      page.locator(".role-form .ui-select-btn"),
      "Viewer",
    );
    await page.getByLabel(/Metrics dashboard only/).check();
    await expect(
      page.getByRole("checkbox", { name: /Trigger & retry pipelines/ }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "Create role", exact: true })
      .click();
    roleCreated = true;
    const roleCard = page.locator(".role-card").filter({ hasText: roleName });
    await expect(roleCard).toBeVisible();
    await expect(roleCard).toContainText("Metrics dashboard only");

    const users = await (
      await page.request.get("/api/users?page_size=200")
    ).json();
    viewerId = users.items.find(
      (user: { email: string }) => user.email === viewerEmail,
    )?.user_id;
    expect(viewerId).toBeTruthy();

    const browser = page.context().browser();
    if (!browser) throw new Error("Browser context is unavailable.");
    viewerContext = await browser.newContext();
    const viewerPage = await viewerContext.newPage();
    await viewerPage.goto("/");
    await viewerPage.getByLabel("Email address").fill(viewerEmail);
    await viewerPage.getByLabel("Password", { exact: true }).fill("demo");
    await viewerPage
      .getByRole("button", { name: "Sign in to workspace" })
      .click();
    await expect(
      viewerPage.getByRole("heading", { name: "Tenant health" }),
    ).toBeVisible();
    await expect(
      viewerPage.getByRole("link", { name: "Tenants", exact: true }),
    ).toBeVisible();

    await page.goto("/admin?section=users");
    const roleSelect = page.getByLabel(`Role for ${viewerEmail}`);
    await chooseSelectOption(
      roleSelect,
      new RegExp(`${roleName} \\(viewer\\)`),
    );
    const confirmation = page.getByRole("dialog", { name: "Change role" });
    await expect(confirmation).toContainText(roleName);
    await confirmation.getByRole("button", { name: "Change role" }).click();
    await expect(roleSelect).toContainText(roleName);

    await expect(
      viewerPage.getByRole("heading", {
        name: "Metrics overview",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      viewerPage.getByRole("heading", { name: "Tenant health metrics" }),
    ).toBeVisible();
    await expect(
      viewerPage.getByText("Success rate", { exact: true }),
    ).toBeVisible();
    await expect(
      viewerPage.getByRole("link", { name: "Tenants", exact: true }),
    ).toHaveCount(0);
    await expect(
      viewerPage.getByRole("textbox", { name: "Search tenants, logs, pages" }),
    ).toHaveCount(0);
    await expect(
      viewerPage.getByRole("button", { name: "Notifications" }),
    ).toHaveCount(0);
    const metricsTenant = viewerPage.getByLabel("Metrics tenant");
    await chooseSelectOption(metricsTenant, "Acme Retail");
    await expect(viewerPage).toHaveURL(/activity_tenant=acme_retail/);
    await expect(
      viewerPage.getByText(
        "Aggregate passed, failed and active runs for Acme Retail",
      ),
    ).toBeVisible();
    await chooseSelectOption(metricsTenant, "All tenants");
    await expect(viewerPage).not.toHaveURL(/activity_tenant=/);
    await viewerPage.screenshot({
      path: path.resolve("../docs/screenshots/metrics-only.png"),
      fullPage: true,
      animations: "disabled",
    });

    const metrics = await viewerPage.request.get("/api/metrics/overview");
    expect(metrics.status()).toBe(200);
    expect(await metrics.json()).not.toHaveProperty("recent_failures");
    expect(
      (
        await viewerPage.request.get("/api/metrics/tenants?page_size=200")
      ).status(),
    ).toBe(200);
    expect(
      (
        await viewerPage.request.get("/api/tenants/acme_retail/metrics")
      ).status(),
    ).toBe(200);
    for (const endpoint of [
      "/api/overview",
      "/api/tenants",
      "/api/runs",
      "/api/users",
    ]) {
      const denied = await viewerPage.request.get(endpoint);
      expect(denied.status(), endpoint).toBe(403);
      expect((await denied.json()).error.code).toBe("metrics_only");
    }
    const viewerIdentity = await (
      await viewerPage.request.get("/api/me")
    ).json();
    const deniedAction = await viewerPage.request.post(
      "/api/runs/not-a-real-run/retry",
      {
        headers: { "X-CSRF-Token": viewerIdentity.csrf_token },
      },
    );
    expect(deniedAction.status()).toBe(403);
    expect((await deniedAction.json()).error.code).toBe("metrics_only");

    await viewerPage.goto("/runs");
    await expect(
      viewerPage.getByText("Metrics-only access", { exact: true }),
    ).toBeVisible();

    await viewerPage.goto("/");
    await viewerPage.setViewportSize({ width: 390, height: 844 });
    await expect(
      viewerPage.getByRole("heading", {
        name: "Metrics overview",
        exact: true,
      }),
    ).toBeVisible();
    const mobileWidth = await viewerPage.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(mobileWidth).toBeLessThanOrEqual(390);
    await viewerPage.screenshot({
      path: path.resolve("../docs/screenshots/metrics-only-mobile.png"),
      fullPage: true,
      animations: "disabled",
    });

    await page.request.patch(`/api/users/${viewerId}`, {
      headers: { "X-CSRF-Token": adminIdentity.csrf_token },
      data: { role: "viewer" },
    });
    await expect(
      viewerPage.getByRole("link", { name: "Tenants", exact: true }),
    ).toBeVisible();
  } finally {
    await viewerContext?.close();
    if (viewerId) {
      await page.request.patch(`/api/users/${viewerId}`, {
        headers: { "X-CSRF-Token": adminIdentity.csrf_token },
        data: { role: "viewer" },
      });
    }
    if (roleCreated) {
      await page.request.delete(`/api/roles/${roleName}`, {
        headers: { "X-CSRF-Token": adminIdentity.csrf_token },
      });
    }
  }
});
