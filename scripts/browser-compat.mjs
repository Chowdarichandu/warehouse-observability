import assert from 'node:assert/strict';
import { webkit } from '../frontend/node_modules/playwright/index.mjs';

// Exercise Safari's engine against the local CI service, without upstream writes.
const browser = await webkit.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://localhost:8080');
  await page.getByRole('button', { name: 'Sign in to workspace' }).waitFor();
  await page.route('**/api/config', route => route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>Gateway unavailable</title>' }));
  await page.reload();
  await page.getByText('The console service returned an unexpected response. Please try again shortly.').waitFor();
  await page.unroute('**/api/config');
  await page.addInitScript(() => { Object.defineProperty(AbortSignal, 'timeout', { value: undefined, configurable: true }); });
  await page.reload();
  await page.getByRole('button', { name: 'Sign in to workspace' }).waitFor();
  assert.deepEqual(errors, [], 'Mobile WebKit emitted uncaught errors');
  console.log(JSON.stringify({ browser: 'mobile WebKit', checks: 3, passed: true }));
  await context.close();
} finally {
  await browser.close();
}
