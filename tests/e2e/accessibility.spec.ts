import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const seriousOrCritical = (
  violations: Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"],
) =>
  violations
    .filter(
      (violation) =>
        violation.impact === "serious" || violation.impact === "critical",
    )
    .map(({ id, impact, description, nodes }) => ({
      id,
      impact,
      description,
      nodes: nodes.map((node) => ({
        target: node.target,
        failureSummary: node.failureSummary,
      })),
    }));

test("design system is axe-clean in light and dark at desktop and mobile widths", async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem("obs-theme", "light"));
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@demo.local");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "demo");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Tenant health" }),
  ).toBeVisible();
  await page.goto("/styleguide");
  await expect(
    page.getByRole("heading", { name: "Design system" }),
  ).toBeVisible();

  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const theme of ["light", "dark"] as const) {
      const currentTheme = await page
        .locator("html")
        .getAttribute("data-theme");
      if (currentTheme !== theme) {
        await page
          .getByRole("button", { name: `Switch to ${theme} theme` })
          .click();
      }
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(
        seriousOrCritical(results.violations),
        `${theme} at ${viewport.width}px`,
      ).toEqual([]);
    }
  }
});
