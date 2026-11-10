import { expect, test } from "@playwright/test";
import { chooseSelectOption } from "./select";

test("quality definitions can be created, investigated, edited, run and disabled", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  const loginResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  const session = (await (await loginResponse).json()) as {
    csrf_token: string;
  };
  await expect(
    page.getByRole("heading", { name: "Tenant health", exact: true }),
  ).toBeVisible();
  await page.goto("/quality?tenant_id=acme_retail");
  await expect(
    page.getByRole("heading", { name: "Data quality", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Simulated evidence, realistic checks"),
  ).toBeVisible();
  const name = `Browser check ${Date.now()}`;
  let id: number | undefined;
  try {
    await page.getByRole("button", { name: "New check", exact: true }).click();
    await chooseSelectOption(
      page.getByLabel("Check tenant", { exact: true }),
      "Acme Retail",
    );
    await page.getByLabel("Check name", { exact: true }).fill(name);
    await page.getByLabel("Sample limit", { exact: true }).fill("100");
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/quality/checks") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Save check", exact: true }).click();
    id = ((await (await created).json()) as { id: number }).id;
    const row = page
      .locator("tbody tr")
      .filter({ has: page.getByRole("button", { name, exact: true }) });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: `Run ${name}`, exact: true }).click();
    await expect(row.locator(".status-pill").first()).toHaveText("failed");
    await row.getByRole("button", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`check_id=${id}`));
    await expect(
      page
        .locator(".quality-evidence")
        .getByText("SIMULATED", { exact: true })
        .first(),
    ).toBeVisible();
    await expect(page.locator(".quality-evidence")).toContainText(
      "bounded sample",
    );
    await row
      .getByRole("button", { name: `Edit ${name}`, exact: true })
      .click();
    await page
      .getByLabel("Maximum violation rate (%)", { exact: true })
      .fill("10");
    await page.getByRole("button", { name: "Save check", exact: true }).click();
    await expect(row).toContainText("Awaiting evaluation");
    await row.getByRole("button", { name: `Run ${name}`, exact: true }).click();
    await expect(row.locator(".status-pill").first()).toHaveText("success");
    await expect(page.locator(".quality-evidence article")).toHaveCount(2);
    await row.getByRole("button", { name: "Disable", exact: true }).click();
    await expect(
      row.getByRole("button", { name: `Run ${name}`, exact: true }),
    ).toBeDisabled();
    await expect(row.locator(".status-pill").first()).toHaveText("success");
    await row.getByRole("button", { name: "Enable", exact: true }).click();
    await expect(
      row.getByRole("button", { name: `Run ${name}`, exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByText("Unable to load this view", { exact: true }),
    ).toHaveCount(0);
  } finally {
    // Keep test-created definitions inactive; a clean demo reset removes test fixtures before capture.
    if (id !== undefined)
      await page.request.patch(`/api/quality/checks/${id}`, {
        data: { enabled: false },
        headers: { "X-CSRF-Token": session.csrf_token },
      });
  }
});
