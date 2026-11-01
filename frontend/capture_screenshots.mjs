import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const baseUrl = (process.env.ATLAS_BASE_URL ?? 'http://127.0.0.1:5173').replace(/\/$/, '');

const outDir = path.resolve(__dirname, '..', 'docs', 'assets', 'screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 3,
  });

  const page = await context.newPage();

  async function prepareCapture() {
    await page.evaluate(() => document.fonts.ready);
    await page.addStyleTag({
      content: `
        html { zoom: 1.18; }
        *, *::before, *::after {
          animation-duration: 0s !important;
          transition-duration: 0s !important;
          caret-color: transparent !important;
        }
      `,
    });
    await page.waitForTimeout(250);
  }

  async function capture(name, options = {}) {
    await prepareCapture();
    await page.screenshot({
      path: path.join(outDir, name),
      fullPage: true,
      animations: 'disabled',
      ...options,
    });
  }

  console.log('1. Capturing login page...');
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' });
  await capture('login.png', { fullPage: false });

  console.log('2. Logging in...');
  await page.fill('input[type="email"]', 'demo@atlasmlops.dev');
  await page.fill('input[type="password"]', 'demo-password-123');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/overview', { timeout: 10000 });
  await page.waitForTimeout(1500);

  // Select the seeded demo project from the app's custom project switcher.
  const projectSwitcher = page.locator('.context-switch').nth(1);
  await projectSwitcher.locator('.dropdown-trigger').click();
  await page.getByRole('menuitem', { name: 'Customer Churn', exact: true }).click();
  await page.waitForTimeout(750);

  console.log('3. Capturing overview dashboard...');
  await capture('overview.png');

  console.log('4. Capturing experiments page...');
  await page.goto(`${baseUrl}/experiments`, { waitUntil: 'networkidle' });
  await capture('experiments.png');

  console.log('5. Capturing monitoring page...');
  await page.goto(`${baseUrl}/monitoring`, { waitUntil: 'networkidle' });
  await capture('monitoring.png');

  console.log('6. Capturing deployments playground...');
  await page.goto(`${baseUrl}/deployments`, { waitUntil: 'networkidle' });
  await prepareCapture();

  // Open an existing deployment (ignore the /new route) and show its prediction playground.
  const deploymentHref = await page.locator('a[href*="/deployments/"]').evaluateAll((links) => {
    const href = links
      .map((link) => link.getAttribute('href'))
      .find(
        (value) => value && value !== '/deployments/new' && /^\/deployments\/[^/?]+$/.test(value),
      );
    return href ?? null;
  });
  if (!deploymentHref) throw new Error('No seeded deployment link was found on the deployments page.');
  await page.goto(`${baseUrl}${deploymentHref}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(750);
  await page.setViewportSize({ width: 1440, height: 1500 });

  // Click 'Test Playground' tab
  const testTab = page.getByRole('button', { name: /Test Playground/ });
  await testTab.click();
  await page.waitForTimeout(250);

  // Click 'Run prediction' button
  await page.getByRole('button', { name: /Run prediction/ }).click();
  await page.getByText(/Prediction returned|Prediction failed/).waitFor({ timeout: 10000 }).catch(() => {});
  await page.getByRole('button', { name: 'Dismiss notification' }).click().catch(() => {});
  await capture('playground.png');

  await browser.close();
  console.log('All high-resolution screenshots captured successfully!');
}

run().catch(err => {
  console.error('Error capturing screenshots:', err);
  process.exit(1);
});
