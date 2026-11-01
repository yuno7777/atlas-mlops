import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // HiDPI 2x Retina quality
  });

  const page = await context.newPage();

  console.log('1. Capturing login page...');
  await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'login.png') });

  console.log('2. Logging in...');
  await page.fill('input[type="email"]', 'demo@atlasmlops.dev');
  await page.fill('input[type="password"]', 'demo-password-123');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/overview', { timeout: 10000 });
  await page.waitForTimeout(1500);

  // Switch project to Customer Churn if select exists
  const projectSelect = await page.$('select');
  if (projectSelect) {
    const options = await page.$$eval('select option', opts => opts.map(o => ({ text: o.textContent, val: o.value })));
    const churnOpt = options.find(o => o.text && o.text.includes('Customer Churn'));
    if (churnOpt) {
      await page.selectOption('select', churnOpt.val);
      await page.waitForTimeout(1500);
    }
  }

  console.log('3. Capturing overview dashboard...');
  await page.screenshot({ path: path.join(outDir, 'overview.png') });

  console.log('4. Capturing experiments page...');
  await page.goto('http://127.0.0.1:5173/experiments', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(outDir, 'experiments.png') });

  console.log('5. Capturing monitoring page...');
  await page.goto('http://127.0.0.1:5173/monitoring', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(outDir, 'monitoring.png') });

  console.log('6. Capturing deployments playground...');
  await page.goto('http://127.0.0.1:5173/deployments', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // Click first deployment link or row
  const deploymentLink = await page.$('a[href*="/deployments/"]');
  if (deploymentLink) {
    await deploymentLink.click();
    await page.waitForTimeout(1000);

    // Click 'Test Playground' tab
    const testTab = await page.$('button:has-text("Test Playground")');
    if (testTab) {
      await testTab.click();
      await page.waitForTimeout(500);
    }

    // Click 'Run prediction' button
    const predictBtn = await page.$('button:has-text("Run prediction")');
    if (predictBtn) {
      await predictBtn.click();
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: path.join(outDir, 'playground.png') });
  }

  await browser.close();
  console.log('All high-resolution screenshots captured successfully!');
}

run().catch(err => {
  console.error('Error capturing screenshots:', err);
  process.exit(1);
});
