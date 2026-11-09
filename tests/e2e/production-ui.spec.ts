import { test, expect } from '@playwright/test';

test('live sign-in presents organization SSO without demo credentials', async ({ page }) => {
  await page.route('**/api/config', (route) => route.fulfill({ json: { mode: 'live', environment: 'Production', auth_provider: 'oidc', live_actions_enabled: false } }));
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Continue with organization SSO' })).toHaveAttribute('href', '/api/auth/oidc/start');
  await expect(page.getByText('Explore the demo', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0);
  await expect(page.getByText('PRODUCTION', { exact: true })).toBeVisible();
});

test('navigation, keyboard search and reduced motion remain accessible', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email address').fill('admin@demo.local');
  await page.getByLabel('Password', { exact: true }).fill(process.env.DEMO_PASSWORD || 'demo');
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Tenant health', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Pipeline runs', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Pipeline runs', exact: true })).toBeVisible();
  await expect(page.locator('#main-content')).toBeFocused();
  await page.keyboard.press('Control+k');
  await expect(page.getByLabel('Search errors and logs')).toBeFocused();
  const duration = await page.locator('.route-enter').evaluate((element) => parseFloat(getComputedStyle(element).animationDuration));
  expect(duration).toBeLessThan(0.001);
  await expect(page.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main-content');
});
