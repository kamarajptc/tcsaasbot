import { chromium } from './dashboard/node_modules/playwright-core/index.js';

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.goto('http://localhost:9101');
  await page.waitForLoadState('networkidle');

  console.log('Page loaded, taking screenshot...');
  await page.screenshot({ path: 'dashboard_screenshot.png', fullPage: true });

  // Check for CONFIGURE buttons
  const configureButtons = await page.$$('text=CONFIGURE');
  console.log('Found', configureButtons.length, 'CONFIGURE buttons');

  if (configureButtons.length > 0) {
    console.log('Clicking first CONFIGURE button...');
    await configureButtons[0].click();
    await page.waitForTimeout(2000);

    // Take another screenshot
    await page.screenshot({ path: 'dashboard_after_click.png', fullPage: true });

    // Check for modal
    const modal = await page.$('.fixed.inset-0.bg-gray-950');
    console.log('Modal found:', !!modal);

    // Check for tabs
    const tabs = await page.$$('button');
    console.log('Found', tabs.length, 'buttons');

    for (let i = 0; i < Math.min(tabs.length, 10); i++) {
      const text = await tabs[i].textContent();
      console.log(`Button ${i}: ${text}`);
    }
  }

  await browser.close();
  console.log('Done');
})();