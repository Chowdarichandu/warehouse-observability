import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

test('capture the remaining console screens', async ({ page }) => {
  const directory = path.resolve('../output/screenshots');
  mkdirSync(directory, { recursive: true });
  await page.goto('/');
  await page.getByLabel('Email address').fill('admin@demo.local');
  await page.getByLabel('Password', { exact: true }).fill(process.env.DEMO_PASSWORD || 'demo');
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Tenant health', exact: true })).toBeVisible();

  const screens = [
    { url: '/tenants', file: 'tenants.png', ready: 'Tenants' },
    { url: '/tenants/acme_retail', file: 'tenant-detail.png', ready: 'Acme Retail' },
    { url: '/runs?status=failed&range=7d', file: 'runs.png', ready: 'Pipeline runs' },
    { url: '/freshness', file: 'freshness.png', ready: 'Data freshness' },
    { url: '/platform', file: 'platform.png', ready: 'Platform health' },
    { url: '/admin', file: 'admin.png', ready: 'Administration' },
    { url: '/search?q=binlog', file: 'search.png', ready: 'Search your pipelines' },
    { url: '/?tv=1', file: 'tv-mode.png', ready: 'Tenant health' },
  ];
  for (const screen of screens) {
    await page.goto(screen.url);
    await expect(page.getByRole('heading', { name: screen.ready, exact: true })).toBeVisible();
    await expect(page.getByRole('status', { name: 'Loading' })).toHaveCount(0);
    await expect(page.getByText('Unable to load this view', { exact: true })).toHaveCount(0);
    await page.screenshot({ path: path.join(directory, screen.file), fullPage: true });
  }
});
