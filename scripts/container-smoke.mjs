import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
});
try {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  const origin = process.env.CONTAINER_URL || 'http://localhost:18080';
  await page.goto(origin);
  await page.getByLabel('Email address').fill('admin@demo.local');
  await page.getByLabel('Password', { exact: true }).fill(process.env.DEMO_PASSWORD || 'demo');
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Tenant health', exact: true })).toBeVisible();
  await expect(page.getByRole('status', { name: 'Loading' })).toHaveCount(0);
  const response = await page.request.get(`${origin}/api/runs?tenant=acme_retail&status=failed`);
  expect(response.ok()).toBeTruthy();
  const runs = await response.json();
  expect(runs.items.length).toBeGreaterThan(0);
  const key = encodeURIComponent(runs.items[0].run_key);
  const logResponse = await page.request.get(`${origin}/api/runs/${key}/log`);
  expect(logResponse.ok()).toBeTruthy();
  const log = await logResponse.json();
  expect(log.redacted).toBe(true);
  expect(log.content).toContain('[REDACTED]');
  await page.goto(`${origin}/runs/${key}`);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByText('Unable to load this view', { exact: true })).toHaveCount(0);
  console.log('Container smoke passed: seeded data, nginx proxy, login, overview, failed run and redacted log.');
} finally {
  await browser.close();
}
