import { test, expect, type Route } from "@playwright/test";

test("unexpected API responses have an actionable message on mobile browsers", async ({
  page,
}) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<!doctype html><title>Gateway cold start</title>",
    }),
  );
  await page.goto("/");
  await expect(
    page.getByText(
      "The console service returned an unexpected response. Please try again shortly.",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("The string did not match the expected pattern."),
  ).toHaveCount(0);
});

test("sign-in works without the AbortSignal.timeout browser extension", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(AbortSignal, "timeout", {
      value: undefined,
      configurable: true,
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Sign in to workspace" }),
  ).toBeVisible();
});

test("live sign-in presents organization SSO without demo credentials", async ({
  page,
}) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: {
        mode: "live",
        environment: "Production",
        auth_provider: "oidc",
        live_actions_enabled: false,
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Continue with organization SSO" }),
  ).toHaveAttribute("href", "/api/auth/oidc/start");
  await expect(page.getByText("Explore the demo", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PRODUCTION", { exact: true })).toBeVisible();
});

test("navigation, keyboard search and reduced motion remain accessible", async ({
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
  await page.getByRole("link", { name: "Pipeline runs", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Pipeline runs", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#main-content")).toBeFocused();
  await page.keyboard.press("Control+k");
  await expect(page.getByLabel("Search tenants, logs, pages")).toBeFocused();
  const duration = await page
    .locator(".route-enter")
    .evaluate((element) =>
      parseFloat(getComputedStyle(element).animationDuration),
    );
  expect(duration).toBeLessThan(0.001);
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toHaveAttribute("href", "#main-content");
});

test("product navigation only shows modules granted to the signed-in user", async ({
  page,
}) => {
  const sapOnlyIdentity = async (route: Route) => {
    const response = await route.fetch();
    if (!response.ok()) return route.fulfill({ response });
    const user = await response.json();
    user.permissions = (Array.isArray(user.permissions) ? user.permissions : [])
      .filter((permission: string) => !permission.startsWith("view_module_"))
      .concat("view_module_sap");
    await route.fulfill({ response, json: user });
  };
  await page.route("**/api/me", sapOnlyIdentity);
  await page.route("**/api/auth/login", sapOnlyIdentity);
  await page.route("**/api/access", async (route) => {
    const response = await route.fetch();
    if (!response.ok()) return route.fulfill({ response });
    const access = await response.json();
    access.modules = [
      ...access.modules.filter(
        (module: { module_id: string }) => module.module_id === "pravah",
      ),
      { module_id: "sap", display_name: "SAP", enabled: true, access: "granted" },
    ];
    await route.fulfill({ response, json: access });
  });
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: /Pravah/ }).click();
  const menu = page.locator("#workspace-product-menu");
  await expect(menu).toBeVisible();
  await expect(menu).toHaveCSS("width", "248px");
  await expect(menu.getByRole("button", { name: /SAP/ })).toBeVisible();
  await expect(menu.getByText("HRMS", { exact: true })).toHaveCount(0);
  await expect(menu.getByText("Finance", { exact: true })).toHaveCount(0);
  await menu.getByRole("button", { name: /SAP/ }).click();
  await expect(menu).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText(
    "SAP access is assigned. This module is not available yet.",
  );
});
