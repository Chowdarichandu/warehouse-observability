import { expect, test } from "@playwright/test";
import type { BrowserContext } from "@playwright/test";

let adminState: Awaited<ReturnType<BrowserContext["storageState"]>>;
test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  adminState = await page.context().storageState();
  await page.close();
});
test.beforeEach(async ({ context }) => {
  await context.addCookies(adminState.cookies);
});

test("onboarding guards URL steps and validates identity and enabled sources", async ({
  page,
}) => {
  await page.goto("/onboarding?step=4");
  await expect(
    page.getByRole("heading", {
      name: "Tell us about your tenant",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page).toHaveURL(/step=1/);
  await expect(page.getByLabel("Display name", { exact: true })).toHaveValue(
    "System Engines",
  );
  await expect(page.getByLabel("Tenant slug", { exact: true })).toHaveValue(
    "system_engines",
  );
  await page
    .getByLabel("Display name", { exact: true })
    .fill("Field Operations");
  await expect(page.getByLabel("Tenant slug", { exact: true })).toHaveValue(
    "field_operations",
  );
  await expect(
    page.getByLabel("Warehouse schema", { exact: true }),
  ).toHaveValue("field_operations");
  await page.getByLabel("Tenant slug", { exact: true }).fill("manual_identity");
  await page
    .getByLabel("Display name", { exact: true })
    .fill("New Display Name");
  await expect(page.getByLabel("Tenant slug", { exact: true })).toHaveValue(
    "manual_identity",
  );
  await page.getByLabel("Owner email", { exact: true }).fill("not-an-email");
  await page.getByLabel("Freshness SLA (minutes)", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByText("Enter a valid owner email address.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Choose a whole number between 5 and 10,080 minutes.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Owner email", { exact: true })
    .fill("data@example.com");
  await page.getByLabel("Freshness SLA (minutes)", { exact: true }).fill("120");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Connect the data sources",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel("Enable MySQL", { exact: true }).uncheck();
  await page.getByLabel("Enable MongoDB", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Select at least one source",
  );
  await page.getByLabel("Enable MySQL", { exact: true }).check();
  await page.getByLabel("MySQL port", { exact: true }).fill("70000");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByText("Choose a port between 1 and 65,535.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("MySQL port", { exact: true })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(
    page.getByLabel("MongoDB database", { exact: true }),
  ).toHaveCount(0);
});

test("failed preflight remains failed and back navigation invalidates readiness", async ({
  page,
}) => {
  let passed = false;
  await page.route("**/api/onboarding/preflight", (route) =>
    route.fulfill({
      json: {
        passed,
        simulated: true,
        checks: [
          { name: "Connectivity", passed: true, message: "Connected." },
          {
            name: "Replication access",
            passed,
            message: passed
              ? "Approved."
              : "Replication permission is missing.",
          },
        ],
      },
    }),
  );
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Resolve the failed checks to continue",
    }),
  ).toBeVisible();
  const failed = page
    .locator(".journey-check-list li")
    .filter({ hasText: "Replication access" });
  await expect(failed).toHaveClass(/is-failed/);
  await expect(failed.getByText("Failed", { exact: true })).toBeVisible();
  await expect(failed.getByText("Passed", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Continue", exact: true }),
  ).toBeDisabled();
  passed = true;
  await page.getByRole("button", { name: "Check again", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your configuration is ready" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ready when you are", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Run pre-flight checks", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Run pre-flight checks", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your configuration is ready" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready when you are", exact: true })).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("button", { name: "Run pre-flight checks", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue", exact: true }),
  ).toBeDisabled();
});

test("seven-DAG execution is resumable and defers CDC until initial success", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const tenant = `journey_test_${Date.now()}`;
  await page.goto("/onboarding");
  await page.getByLabel("Display name", { exact: true }).fill("Journey Proof");
  await page.getByLabel("Tenant slug", { exact: true }).fill(tenant);
  await page.getByLabel("Warehouse schema", { exact: true }).fill(tenant);
  await page
    .getByRole("checkbox", { name: /Run initial loads after provisioning/ })
    .uncheck();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Enable MongoDB", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your configuration is ready" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByText("Wait for explicit start", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Start onboarding", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`tenant=${tenant}`));
  await expect(
    page.getByRole("progressbar", { name: "Onboarding DAG completion" }),
  ).toHaveAttribute("aria-valuemax", "7");
  await expect(
    page.getByRole("heading", {
      name: "Provisioned. Initial load is waiting.",
      exact: true,
    }),
  ).toBeVisible({ timeout: 75_000 });
  await expect(
    page.getByRole("heading", { name: "Your tenant is ready", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".journey-dag")).toHaveCount(7);
  const before = await (
    await page.request.get(`/api/onboarding/${tenant}`)
  ).json();
  expect(before.dags).toHaveLength(7);
  expect(
    before.dags
      .filter(
        (dag: { source_type: string; status: string }) =>
          dag.source_type === "mongo",
      )
      .every((dag: { status: string }) => dag.status === "skipped"),
  ).toBeTruthy();
  expect(
    before.dags.find((dag: { node_id: string }) => dag.node_id === "mysql_cdc")
      .status,
  ).toBe("blocked");
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: "Provisioned. Initial load is waiting.",
      exact: true,
    }),
  ).toBeVisible();
  const restored = await (
    await page.request.get(`/api/onboarding/${tenant}`)
  ).json();
  expect(restored.workflow_id).toBe(before.workflow_id);
  await page
    .getByRole("button", { name: "Start initial loads", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your tenant is ready", exact: true }),
  ).toBeVisible({ timeout: 75_000 });
  await expect(
    page.getByRole("link", { name: "Inspect child run", exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".journey-history")).toContainText(
    "Execution timeline",
  );
});
