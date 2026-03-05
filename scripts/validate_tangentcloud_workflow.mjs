#!/usr/bin/env node
/**
 * TangentCloud Workflow Validation Script
 *
 * Validates the core workflow features are accessible and functional
 */

import { createRequire } from 'node:module';
import path from 'path';
import fs from 'fs';

const DASHBOARD_DIR = path.join(process.cwd(), 'dashboard');
const requireFromDashboard = createRequire(path.join(DASHBOARD_DIR, 'package.json'));
const { chromium } = requireFromDashboard('playwright-core');

const DASHBOARD_URL = 'http://localhost:9101';
const TEST_RESULTS = [];

class WorkflowValidator {
    constructor() {
        this.browser = null;
        this.page = null;
    }

    log(message, status = 'INFO') {
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] ${status}: ${message}`;
        console.log(logMessage);
        TEST_RESULTS.push({ timestamp, status, message });
    }

    async init() {
        this.log('Initializing Workflow Validator');
        this.browser = await chromium.launch({ headless: false });
        this.page = await this.browser.newPage();
        await this.page.setViewportSize({ width: 1280, height: 720 });
    }

    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
        this.generateReport();
    }

    generateReport() {
        const reportPath = path.join(process.cwd(), 'workflow_validation_report.json');
        const summary = {
            totalTests: TEST_RESULTS.length,
            passed: TEST_RESULTS.filter(r => r.status === 'PASS').length,
            failed: TEST_RESULTS.filter(r => r.status === 'FAIL').length,
            timestamp: new Date().toISOString(),
            results: TEST_RESULTS
        };

        fs.writeFileSync(reportPath, JSON.stringify(summary, null, 2));
        console.log(`\n📊 Validation Report Generated: ${reportPath}`);
        console.log(`✅ Passed: ${summary.passed}, ❌ Failed: ${summary.failed}`);
    }

    async validateDashboardAccess() {
        this.log('🔍 Validating Dashboard Access');

        try {
            await this.page.goto(DASHBOARD_URL);
            await this.page.waitForLoadState('networkidle');

            const title = await this.page.title();
            if (title.includes('TangentCloud')) {
                this.log('Dashboard loaded successfully', 'PASS');
                return true;
            } else {
                this.log(`Unexpected page title: ${title}`, 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Dashboard access failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async validateBotPresence() {
        this.log('🔍 Validating Bot Presence');

        try {
            // Look for bot cards
            const botCards = await this.page.$$('.bg-white.border');
            if (botCards.length > 0) {
                this.log(`Found ${botCards.length} bot(s) on dashboard`, 'PASS');
                return true;
            } else {
                this.log('No bots found on dashboard', 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Bot presence check failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async validateConfigurationAccess() {
        this.log('🔍 Validating Configuration Access');

        try {
            // Find CONFIGURE button
            const configureButtons = await this.page.$$('text=CONFIGURE');
            if (configureButtons.length === 0) {
                this.log('No CONFIGURE buttons found', 'FAIL');
                return false;
            }

            await configureButtons[0].click();
            await this.page.waitForTimeout(2000);

            // Check if configuration modal opened
            const modal = await this.page.$('.fixed.inset-0.bg-gray-950\\/50');
            if (modal) {
                this.log('Configuration modal opened successfully', 'PASS');
                return true;
            } else {
                this.log('Configuration modal did not open', 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Configuration access failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async validateConfigurationTabs() {
        this.log('🔍 Validating Configuration Tabs');

        try {
            const expectedTabs = [
                'Assistant Configuration',
                'Live Chat',
                'Story Builder',
                'Canned Responses',
                'Small Talk',
                'Data Collection',
                'Integrations'
            ];

            let foundTabs = 0;
            for (const tabName of expectedTabs) {
                const tab = await this.page.$(`text=${tabName}`);
                if (tab) {
                    foundTabs++;
                    this.log(`✓ Found tab: ${tabName}`, 'PASS');
                } else {
                    this.log(`✗ Missing tab: ${tabName}`, 'FAIL');
                }
            }

            if (foundTabs === expectedTabs.length) {
                this.log(`All ${expectedTabs.length} configuration tabs found`, 'PASS');
                return true;
            } else {
                this.log(`Only ${foundTabs}/${expectedTabs.length} tabs found`, 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Tab validation failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async validateAssistantConfiguration() {
        this.log('🔍 Validating Assistant Configuration Tab');

        try {
            // Click on Assistant Configuration tab
            const assistantTab = await this.page.$('text=Assistant Configuration');
            if (assistantTab) {
                await assistantTab.click();
                await this.page.waitForTimeout(1000);
            }

            // Check for welcome message input
            const textareas = await this.page.$$('textarea');
            if (textareas.length > 0) {
                this.log('Welcome message input field found', 'PASS');

                // Test editing welcome message
                const testMessage = 'Welcome to TangentCloud! How can I help you?';
                await textareas[0].fill(testMessage);

                // Check for save button
                const saveButton = await this.page.$('button:has-text("Save")');
                if (saveButton) {
                    this.log('Save functionality available', 'PASS');
                    return true;
                } else {
                    this.log('Save button not found', 'FAIL');
                    return false;
                }
            } else {
                this.log('Welcome message input not found', 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Assistant Configuration validation failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async validateSimulation() {
        this.log('🔍 Validating Chat Simulation');

        try {
            // Close configuration modal first
            const closeButtons = await this.page.$$('button svg.lucide-x');
            if (closeButtons.length > 0) {
                await closeButtons[0].click();
                await this.page.waitForTimeout(1000);
            }

            // Find SIMULATE button
            const simulateButtons = await this.page.$$('text=SIMULATE');
            if (simulateButtons.length === 0) {
                this.log('No SIMULATE buttons found', 'FAIL');
                return false;
            }

            await simulateButtons[0].click();
            await this.page.waitForTimeout(2000);

            // Check if chat window opened
            const chatWindow = await this.page.$('.fixed.inset-0.bg-gray-950\\/50');
            if (chatWindow) {
                this.log('Chat simulation window opened', 'PASS');

                // Check for welcome message
                const welcomeText = await this.page.$('text=Welcome to TangentCloud');
                if (welcomeText) {
                    this.log('Welcome message displayed correctly', 'PASS');
                    return true;
                } else {
                    this.log('Welcome message not found in chat', 'FAIL');
                    return false;
                }
            } else {
                this.log('Chat simulation window did not open', 'FAIL');
                return false;
            }
        } catch (error) {
            this.log(`Simulation validation failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async runValidation() {
        await this.init();

        try {
            const validations = [
                { name: 'Dashboard Access', method: this.validateDashboardAccess.bind(this) },
                { name: 'Bot Presence', method: this.validateBotPresence.bind(this) },
                { name: 'Configuration Access', method: this.validateConfigurationAccess.bind(this) },
                { name: 'Configuration Tabs', method: this.validateConfigurationTabs.bind(this) },
                { name: 'Assistant Configuration', method: this.validateAssistantConfiguration.bind(this) },
                { name: 'Chat Simulation', method: this.validateSimulation.bind(this) }
            ];

            for (const validation of validations) {
                this.log(`\n🚀 Running ${validation.name} Validation`);
                const success = await validation.method();
                if (!success) {
                    this.log(`${validation.name} validation failed`, 'WARN');
                }
            }

        } catch (error) {
            this.log(`Validation suite failed: ${error.message}`, 'FAIL');
        } finally {
            await this.cleanup();
        }
    }
}

// Run the validation
async function main() {
    console.log('🎯 TangentCloud Workflow Validation');
    console.log('====================================');

    const validator = new WorkflowValidator();
    await validator.runValidation();
}

main().catch(console.error);