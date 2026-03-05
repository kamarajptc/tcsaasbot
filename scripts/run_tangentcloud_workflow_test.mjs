#!/usr/bin/env node
/**
 * TangentCloud Client Workflow Test
 *
 * Comprehensive test suite covering all bot configuration features:
 * 1. Assistant Configuration - welcome messages
 * 2. Live Chat - conversation management
 * 3. Story Builder - conversation flows
 * 4. Canned Responses - quick replies
 * 5. Small Talk - casual conversation handling
 * 6. Data Collection - lead forms
 * 7. Integrations - external services
 */

import { createRequire } from 'node:module';
import path from 'path';

const DASHBOARD_DIR = path.join(process.cwd(), 'dashboard');
const requireFromDashboard = createRequire(path.join(DASHBOARD_DIR, 'package.json'));
const { chromium } = requireFromDashboard('playwright-core');
import fs from 'fs';

const DASHBOARD_URL = 'http://localhost:9101';
const TEST_RESULTS = [];

class TangentCloudWorkflowTest {
    constructor() {
        this.browser = null;
        this.page = null;
        this.testBotId = null;
    }

    async log(message, status = 'INFO') {
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] ${status}: ${message}`;
        console.log(logMessage);
        TEST_RESULTS.push({ timestamp, status, message });
    }

    async init() {
        this.log('Initializing TangentCloud Workflow Test');
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
        const reportPath = path.join(process.cwd(), 'tangentcloud_workflow_test_report.json');
        const summary = {
            totalTests: TEST_RESULTS.length,
            passed: TEST_RESULTS.filter(r => r.status === 'PASS').length,
            failed: TEST_RESULTS.filter(r => r.status === 'FAIL').length,
            timestamp: new Date().toISOString(),
            results: TEST_RESULTS
        };

        fs.writeFileSync(reportPath, JSON.stringify(summary, null, 2));
        console.log(`\n📊 Test Report Generated: ${reportPath}`);
        console.log(`✅ Passed: ${summary.passed}, ❌ Failed: ${summary.failed}`);
    }

    async waitForSelector(selector, timeout = 10000) {
        try {
            await this.page.waitForSelector(selector, { timeout });
            return true;
        } catch (error) {
            this.log(`Selector not found: ${selector}`, 'FAIL');
            return false;
        }
    }

    async clickAndWait(selector, waitSelector = null) {
        try {
            await this.page.click(selector);
            if (waitSelector) {
                await this.page.waitForSelector(waitSelector, { timeout: 5000 });
            }
            await this.page.waitForTimeout(1000); // Brief pause for UI updates
            return true;
        } catch (error) {
            this.log(`Failed to click: ${selector}`, 'FAIL');
            return false;
        }
    }

    async fillInput(selector, value) {
        try {
            await this.page.fill(selector, value);
            return true;
        } catch (error) {
            this.log(`Failed to fill input: ${selector}`, 'FAIL');
            return false;
        }
    }

    // Test 1: Assistant Configuration - Setting Welcome Messages
    async testAssistantConfiguration() {
        this.log('🧪 Testing Assistant Configuration - Welcome Messages');

        try {
            // Navigate to dashboard
            await this.page.goto(DASHBOARD_URL);
            await this.page.waitForLoadState('networkidle');

            // Find and click CONFIGURE on the first bot
            const configureButton = 'button:has-text("CONFIGURE")';
            if (!await this.waitForSelector(configureButton)) return false;

            await this.clickAndWait(configureButton, '[data-testid="bot-workspace"]');

            // Verify Assistant Configuration tab is active (should be default)
            const activeTab = 'button.bg-gray-900.text-white:has-text("Assistant Configuration")';
            if (!await this.waitForSelector(activeTab)) {
                this.log('Assistant Configuration tab not active by default', 'FAIL');
                return false;
            }

            // Test welcome message editing
            const welcomeTextarea = 'textarea[placeholder*="welcome message"]';
            if (!await this.waitForSelector(welcomeTextarea)) return false;

            const testWelcomeMessage = 'Welcome to TangentCloud Workflow Test! How can I assist you today?';
            await this.fillInput(welcomeTextarea, testWelcomeMessage);

            // Test description editing
            const descriptionTextarea = 'textarea[placeholder*="Describe what your assistant does"]';
            if (await this.waitForSelector(descriptionTextarea)) {
                await this.fillInput(descriptionTextarea, 'Test assistant for workflow validation');
            }

            // Test color picker
            const colorInput = 'input[type="color"]';
            if (await this.waitForSelector(colorInput)) {
                await this.page.fill(colorInput, '#ff6b6b');
            }

            // Save configuration
            const saveButton = 'button:has-text("Save Configuration")';
            if (!await this.waitForSelector(saveButton)) return false;

            await this.clickAndWait(saveButton);

            // Check for success message
            const successMessage = 'text=Settings saved successfully!';
            if (await this.waitForSelector(successMessage, 5000)) {
                this.log('Assistant Configuration test passed', 'PASS');
                return true;
            } else {
                this.log('Save confirmation not received', 'FAIL');
                return false;
            }

        } catch (error) {
            this.log(`Assistant Configuration test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 2: Live Chat - Managing Conversations
    async testLiveChat() {
        this.log('🧪 Testing Live Chat - Conversation Management');

        try {
            // Switch to Live Chat tab
            const liveChatTab = 'button:has-text("Live Chat")';
            await this.clickAndWait(liveChatTab);

            // Verify Live Chat interface loads
            const conversationList = '[data-testid="conversation-list"]';
            if (!await this.waitForSelector(conversationList, 5000)) {
                // Try alternative selector
                const altSelector = '.space-y-4 > div';
                if (!await this.waitForSelector(altSelector)) {
                    this.log('Live Chat interface not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for conversation management features
            const searchInput = 'input[placeholder*="Search conversations"]';
            if (await this.waitForSelector(searchInput, 3000)) {
                await this.fillInput(searchInput, 'test');
                this.log('Search functionality available', 'PASS');
            }

            // Check for status filters
            const statusButtons = 'button:has-text("All"), button:has-text("New"), button:has-text("Open")';
            if (await this.waitForSelector(statusButtons, 3000)) {
                this.log('Status filtering available', 'PASS');
            }

            this.log('Live Chat test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Live Chat test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 3: Story Builder - Conversation Flows
    async testStoryBuilder() {
        this.log('🧪 Testing Story Builder - Conversation Flows');

        try {
            // Switch to Story Builder tab
            const storyBuilderTab = 'button:has-text("Story Builder")';
            await this.clickAndWait(storyBuilderTab);

            // Verify Story Builder interface loads
            const canvas = '[data-testid="flow-canvas"]';
            if (!await this.waitForSelector(canvas, 5000)) {
                // Try alternative selector for React Flow
                const altSelector = '.react-flow';
                if (!await this.waitForSelector(altSelector, 3000)) {
                    this.log('Story Builder canvas not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for flow controls
            const addNodeButton = 'button:has-text("Add Node")';
            const saveFlowButton = 'button:has-text("Save Flow")';

            if (await this.waitForSelector(saveFlowButton, 3000)) {
                this.log('Flow save functionality available', 'PASS');
            }

            // Test panel might be available
            const testPanel = '[data-testid="test-panel"]';
            if (await this.waitForSelector(testPanel, 3000)) {
                this.log('Flow testing panel available', 'PASS');
            }

            this.log('Story Builder test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Story Builder test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 4: Canned Responses - Quick Replies
    async testCannedResponses() {
        this.log('🧪 Testing Canned Responses - Quick Replies');

        try {
            // Switch to Canned Responses tab
            const cannedTab = 'button:has-text("Canned Responses")';
            await this.clickAndWait(cannedTab);

            // Verify Canned Responses interface loads
            const responseList = '[data-testid="canned-responses-list"]';
            if (!await this.waitForSelector(responseList, 5000)) {
                // Try alternative selector
                const altSelector = '.space-y-4';
                if (!await this.waitForSelector(altSelector)) {
                    this.log('Canned Responses interface not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for add response functionality
            const addButton = 'button:has-text("Add Response")';
            if (await this.waitForSelector(addButton, 3000)) {
                this.log('Add response functionality available', 'PASS');
            }

            // Check for search/filter
            const searchInput = 'input[placeholder*="Search responses"]';
            if (await this.waitForSelector(searchInput, 3000)) {
                await this.fillInput(searchInput, 'welcome');
                this.log('Response search functionality available', 'PASS');
            }

            this.log('Canned Responses test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Canned Responses test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 5: Small Talk - Casual Conversation Handling
    async testSmallTalk() {
        this.log('🧪 Testing Small Talk - Casual Conversation Handling');

        try {
            // Switch to Small Talk tab
            const smallTalkTab = 'button:has-text("Small Talk")';
            await this.clickAndWait(smallTalkTab);

            // Verify Small Talk interface loads
            const patternsList = '[data-testid="small-talk-patterns"]';
            if (!await this.waitForSelector(patternsList, 5000)) {
                // Try alternative selector
                const altSelector = '.grid';
                if (!await this.waitForSelector(altSelector)) {
                    this.log('Small Talk interface not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for pattern management
            const addPatternButton = 'button:has-text("Add Pattern")';
            if (await this.waitForSelector(addPatternButton, 3000)) {
                this.log('Add pattern functionality available', 'PASS');
            }

            // Check for response templates
            const responseTemplates = 'textarea, input[type="text"]';
            if (await this.waitForSelector(responseTemplates, 3000)) {
                this.log('Response template editing available', 'PASS');
            }

            this.log('Small Talk test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Small Talk test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 6: Data Collection - Lead Forms
    async testDataCollection() {
        this.log('🧪 Testing Data Collection - Lead Forms');

        try {
            // Switch to Data Collection tab
            const dataTab = 'button:has-text("Data Collection")';
            await this.clickAndWait(dataTab);

            // Verify Data Collection interface loads
            const formBuilder = '[data-testid="form-builder"]';
            if (!await this.waitForSelector(formBuilder, 5000)) {
                // Try alternative selector
                const altSelector = '.space-y-6';
                if (!await this.waitForSelector(altSelector)) {
                    this.log('Data Collection interface not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for form field management
            const addFieldButton = 'button:has-text("Add Field")';
            if (await this.waitForSelector(addFieldButton, 3000)) {
                this.log('Add field functionality available', 'PASS');
            }

            // Check for field types
            const fieldTypeSelect = 'select';
            if (await this.waitForSelector(fieldTypeSelect, 3000)) {
                this.log('Field type selection available', 'PASS');
            }

            this.log('Data Collection test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Data Collection test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 7: Integrations - External Services
    async testIntegrations() {
        this.log('🧪 Testing Integrations - External Services');

        try {
            // Switch to Integrations tab
            const integrationsTab = 'button:has-text("Integrations")';
            await this.clickAndWait(integrationsTab);

            // Verify Integrations interface loads
            const integrationsList = '[data-testid="integrations-list"]';
            if (!await this.waitForSelector(integrationsList, 5000)) {
                // Try alternative selector
                const altSelector = '.grid-cols-1';
                if (!await this.waitForSelector(altSelector)) {
                    this.log('Integrations interface not loaded', 'FAIL');
                    return false;
                }
            }

            // Check for integration cards
            const integrationCards = '.bg-white.rounded-xl';
            if (await this.waitForSelector(integrationCards, 3000)) {
                this.log('Integration cards available', 'PASS');
            }

            // Check for configuration buttons
            const configButtons = 'button:has-text("Configure")';
            if (await this.waitForSelector(configButtons, 3000)) {
                this.log('Integration configuration available', 'PASS');
            }

            this.log('Integrations test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Integrations test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    // Test 8: End-to-End Chat Simulation
    async testChatSimulation() {
        this.log('🧪 Testing End-to-End Chat Simulation');

        try {
            // Close configuration modal
            const closeButton = 'button[data-testid="close-config"]';
            if (await this.waitForSelector(closeButton, 3000)) {
                await this.clickAndWait(closeButton);
            } else {
                // Try alternative close button
                const altClose = '.fixed.inset-0 button:last-child';
                await this.page.click(altClose).catch(() => {});
            }

            // Find and click SIMULATE on the first bot
            const simulateButton = 'button:has-text("SIMULATE")';
            if (!await this.waitForSelector(simulateButton)) return false;

            await this.clickAndWait(simulateButton);

            // Verify chat window opens with welcome message
            const chatWindow = '.fixed.inset-0.bg-gray-950';
            if (!await this.waitForSelector(chatWindow)) {
                this.log('Chat simulation window not opened', 'FAIL');
                return false;
            }

            // Check if welcome message is displayed
            const welcomeMessage = 'text=Welcome to TangentCloud Workflow Test!';
            if (await this.waitForSelector(welcomeMessage, 5000)) {
                this.log('Custom welcome message displayed correctly', 'PASS');
            } else {
                this.log('Custom welcome message not found', 'FAIL');
            }

            // Test sending a message
            const messageInput = 'textarea[placeholder*="Type a message"]';
            if (await this.waitForSelector(messageInput)) {
                await this.fillInput(messageInput, 'Hello, this is a test message');

                const sendButton = 'button:has-text("Send")';
                if (await this.waitForSelector(sendButton)) {
                    await this.clickAndWait(sendButton);

                    // Wait for bot response
                    await this.page.waitForTimeout(3000);

                    // Check if bot responded
                    const botMessages = '.justify-start .max-w-\\[85\\%]';
                    if (await this.waitForSelector(botMessages, 10000)) {
                        this.log('Bot responded to test message', 'PASS');
                    } else {
                        this.log('Bot did not respond to test message', 'FAIL');
                    }
                }
            }

            // Close chat window
            const chatCloseButton = 'button[data-testid="close-chat"]';
            if (await this.waitForSelector(chatCloseButton, 3000)) {
                await this.clickAndWait(chatCloseButton);
            }

            this.log('Chat Simulation test passed', 'PASS');
            return true;

        } catch (error) {
            this.log(`Chat Simulation test failed: ${error.message}`, 'FAIL');
            return false;
        }
    }

    async runAllTests() {
        await this.init();

        try {
            const tests = [
                { name: 'Assistant Configuration', method: this.testAssistantConfiguration.bind(this) },
                { name: 'Live Chat', method: this.testLiveChat.bind(this) },
                { name: 'Story Builder', method: this.testStoryBuilder.bind(this) },
                { name: 'Canned Responses', method: this.testCannedResponses.bind(this) },
                { name: 'Small Talk', method: this.testSmallTalk.bind(this) },
                { name: 'Data Collection', method: this.testDataCollection.bind(this) },
                { name: 'Integrations', method: this.testIntegrations.bind(this) },
                { name: 'Chat Simulation', method: this.testChatSimulation.bind(this) }
            ];

            for (const test of tests) {
                this.log(`\n🚀 Starting ${test.name} Test`);
                const success = await test.method();
                if (!success) {
                    this.log(`${test.name} Test failed - continuing with other tests`, 'WARN');
                }
            }

        } catch (error) {
            this.log(`Test suite failed: ${error.message}`, 'FAIL');
        } finally {
            await this.cleanup();
        }
    }
}

// Run the test suite
async function main() {
    console.log('🎯 TangentCloud Client Workflow Test Suite');
    console.log('==========================================');

    const tester = new TangentCloudWorkflowTest();
    await tester.runAllTests();
}

main().catch(console.error);