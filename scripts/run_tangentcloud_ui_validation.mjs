#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const REPO_ROOT = "/Users/kamarajp/TCSAASBOT";
const REPORTS_DIR = path.join(REPO_ROOT, "docs", "reports");
const DASHBOARD_DIR = path.join(REPO_ROOT, "dashboard");
const CHAT_URL = "http://127.0.0.1:9101/chat/1";
const CASE_DUMP_CMD = path.join(REPO_ROOT, "scripts", "run_tangentcloud_validation.py");
const CHROMIUM_PATH = "/Users/kamarajp/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const UI_DELAY_MS = 2600;
const requireFromDashboard = createRequire(path.join(DASHBOARD_DIR, "package.json"));
const { chromium } = requireFromDashboard("playwright-core");

function loadCases() {
  const raw = execFileSync("python3", [CASE_DUMP_CMD, "--dump-cases"], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return JSON.parse(raw);
}

function passes(testCase, answer, status = "ok") {
  const lowered = (answer || "").toLowerCase();
  const missing = (testCase.expected_contains || []).filter((token) => !lowered.includes(String(token).toLowerCase()));
  const forbidden = (testCase.forbidden_contains || []).filter((token) => lowered.includes(String(token).toLowerCase()));
  const notes = [];
  if (status !== "ok") notes.push(`ui_status=${status}`);
  if (missing.length) notes.push(`missing=${JSON.stringify(missing)}`);
  if (forbidden.length) notes.push(`forbidden=${JSON.stringify(forbidden)}`);
  return { passed: notes.length === 0, notes: notes.join("; ") || testCase.notes || "" };
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

async function waitForBotReply(page, previousBotCount) {
  const botBubbleSelector = "main .justify-start .max-w-\\[85\\%\\]";
  await page.waitForFunction(
    ({ selector, previous }) => document.querySelectorAll(selector).length > previous,
    { selector: botBubbleSelector, previous: previousBotCount },
    { timeout: 45000 }
  );
  const botReplies = await page.locator(botBubbleSelector).allInnerTexts();
  return botReplies[botReplies.length - 1]?.trim() || "";
}

async function run() {
  fs.mkdirSync(REPORTS_DIR, { recursive: true });
  const cases = loadCases();
  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  await page.goto(CHAT_URL, { waitUntil: "networkidle" });

  const textarea = page.locator("textarea");
  await textarea.waitFor({ state: "visible", timeout: 30000 });

  const rows = [];
  for (const testCase of cases) {
    const botBubbleSelector = "main .justify-start .max-w-\\[85\\%\\]";
    const previousBotCount = await page.locator(botBubbleSelector).count();
    const started = Date.now();
    let answer = "";
    let uiStatus = "ok";
    try {
      await textarea.fill(testCase.question);
      await textarea.press("Enter");
      answer = await waitForBotReply(page, previousBotCount);
    } catch (error) {
      uiStatus = "error";
      answer = String(error);
    }

    const latencyMs = Date.now() - started;
    const result = passes(testCase, answer, uiStatus);
    rows.push({
      run_at_utc: new Date().toISOString(),
      execution_mode: "ui_chatbot",
      case_id: testCase.case_id,
      scenario: testCase.scenario,
      category: testCase.category,
      question: testCase.question,
      expected_contains: (testCase.expected_contains || []).join(" | "),
      forbidden_contains: (testCase.forbidden_contains || []).join(" | "),
      ui_status: uiStatus,
      passed: result.passed,
      latency_ms: latencyMs,
      answer,
      evaluation_notes: result.notes,
    });
    await page.waitForTimeout(UI_DELAY_MS);
  }

  await browser.close();

  const csvPath = path.join(REPORTS_DIR, "tangentcloud_ui_validation_results.csv");
  const summaryPath = path.join(REPORTS_DIR, "tangentcloud_ui_validation_summary.json");
  const headers = [
    "run_at_utc",
    "execution_mode",
    "case_id",
    "scenario",
    "category",
    "question",
    "expected_contains",
    "forbidden_contains",
    "ui_status",
    "passed",
    "latency_ms",
    "answer",
    "evaluation_notes",
  ];
  const csvLines = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")),
  ];
  fs.writeFileSync(csvPath, `${csvLines.join("\n")}\n`, "utf-8");

  const byScenario = {};
  for (const row of rows) {
    byScenario[row.scenario] ||= { total: 0, passed: 0, failed: 0 };
    byScenario[row.scenario].total += 1;
    if (row.passed) byScenario[row.scenario].passed += 1;
    else byScenario[row.scenario].failed += 1;
  }
  const summary = {
    total: rows.length,
    passed: rows.filter((row) => row.passed).length,
    failed: rows.filter((row) => !row.passed).length,
    generated_at_utc: new Date().toISOString(),
    execution_mode: "ui_chatbot",
    chat_url: CHAT_URL,
    by_scenario: byScenario,
  };
  fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf-8");

  console.log(csvPath);
  console.log(summaryPath);
  console.log(JSON.stringify(summary, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
