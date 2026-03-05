#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const REPO_ROOT = "/Users/kamarajp/TCSAASBOT";
const DASHBOARD_DIR = path.join(REPO_ROOT, "dashboard");
const REPORTS_DIR = path.join(REPO_ROOT, "docs", "reports");
const DASHBOARD_URL = "http://127.0.0.1:9101/?start=dashboard";
const LOGIN_URL = "http://127.0.0.1:9100/api/v1/auth/login";
const CHROMIUM_PATH = "/Users/kamarajp/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const requireFromDashboard = createRequire(path.join(DASHBOARD_DIR, "package.json"));
const { chromium } = requireFromDashboard("playwright-core");

async function login() {
  const response = await fetch(LOGIN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "ops@tangentcloud.in", password: "password123" }),
  });
  if (!response.ok) {
    throw new Error(`Login failed with ${response.status}`);
  }
  return response.json();
}

async function run() {
  fs.mkdirSync(REPORTS_DIR, { recursive: true });
  const auth = await login();

  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  await page.addInitScript((token) => {
    window.localStorage.setItem("access_token", token);
  }, auth.access_token);

  const result = {
    generated_at_utc: new Date().toISOString(),
    dashboard_url: DASHBOARD_URL,
    checks: [],
  };

  try {
    await page.goto(DASHBOARD_URL, { waitUntil: "networkidle" });
    await page.locator("button").filter({ hasText: /^Agents$/i }).first().click();
    const configureButton = page
      .locator("button")
      .filter({ hasText: /configure/i })
      .first();
    await configureButton.waitFor({ state: "visible", timeout: 30000 });
    await configureButton.click();

    await page.locator("button").filter({ hasText: /live chat/i }).first().click();
    await page.getByRole("heading", { name: "Inbox" }).waitFor({ state: "visible", timeout: 15000 });

    const conversationButtons = page.locator("button").filter({ hasText: "Conversation #" });
    const count = await conversationButtons.count();
    result.checks.push({ name: "inbox_has_rows", passed: count > 0, observed: count });

    await page.locator("input[placeholder='Type a message...']").waitFor({ state: "visible", timeout: 15000 });
    result.checks.push({ name: "message_input_visible", passed: true });

    const emptyStateVisible = await page.getByText("Select a conversation").isVisible().catch(() => false);
    result.checks.push({ name: "blank_state_hidden_when_rows_exist", passed: !emptyStateVisible, observed: emptyStateVisible });

    const previewCount = await page.locator("button p.text-sm.text-gray-500").evaluateAll((nodes) =>
      nodes.filter((node) => /^(Visitor|Assistant|Agent):/.test(node.textContent || "")).length
    );
    result.checks.push({ name: "sender_prefixed_previews_present", passed: previewCount > 0, observed: previewCount });
  } finally {
    await browser.close();
  }

  result.passed = result.checks.every((item) => item.passed);
  const outPath = path.join(REPORTS_DIR, "live_chat_workspace_validation.json");
  fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`, "utf-8");
  console.log(outPath);
  console.log(JSON.stringify(result, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
