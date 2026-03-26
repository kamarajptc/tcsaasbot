import axios from 'axios';

const api = axios.create({
    // During local development default to the backend started by `start_all.sh`.
    baseURL: process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === 'development' ? 'http://localhost:9100' : '/api/v1'),
});

export const isValidToken = (token: string | null): boolean => {
    if (!token) return false;
    try {
        const parts = token.split('.');
        if (parts.length !== 3) return false;
        const payloadBase64 = parts[1];
        // Handle unpadded base64 data
        let base64 = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
        while (base64.length % 4) {
            base64 += '=';
        }
        const decodedJson = JSON.parse(globalThis.atob(base64));
        const exp = decodedJson.exp;
        if (!exp) return true; // Assumed valid if no expiration
        return (Date.now() / 1000) < exp;
    } catch (e) {
        return false;
    }
};

// Request interceptor to add API Key/Token
api.interceptors.request.use((config) => {
    // In a real app, this would be retrieved from auth state/secure storage
    const isBrowser = typeof window !== 'undefined';
    const token = isBrowser ? (globalThis.localStorage?.getItem ? globalThis.localStorage.getItem('access_token') : null) : null;
    if (token) {
        config.headers['Authorization'] = `Bearer ${token}`;
    }
    // config.headers['X-API-Key'] = apiKey || 'demo_tenant_key'; // Deprecated
    return config;
});

// Response interceptor for global error handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401 || error.response?.status === 403) {
            console.error('Authentication Error: Session expired or invalid API key.');
            if (globalThis.window) {
                const wasLoggedIn = !!localStorage.getItem('access_token');
                localStorage.removeItem('access_token');
                localStorage.removeItem('tcsaas_api_key');
                
                // Only force a reload if we were previously logged in or not on the landing/onboarding page
                // to avoid infinite loops on the landing page itself
                const isAuthPage = window.location.pathname.includes('/onboarding');
                const isAlreadyLanding = window.location.search.includes('start=landing');
                
                if (!isAuthPage && !isAlreadyLanding && wasLoggedIn) {
                    window.location.href = '/?start=landing';
                }
            }
        }
        return Promise.reject(error);
    }
);


export const dashboardApi = {
    login: async (username: string, password: string): Promise<{ access_token: string, token_type: string }> => {
        const response = await api.post('/auth/login', { username, password });
        return response.data;
    },
    createBot: async (data: { name: string; description?: string; prompt_template?: string; response_mode?: 'knowledge_only' | 'knowledge_plus_reasoning'; welcome_message?: string; primary_color?: string; tools?: string[] }) => {
        // Hardcode tenant_id for MVP if auth not ready
        return api.post('/dashboard/', data);
    },
    updateBot: async (id: number, data: any) => {
        return api.put(`/dashboard/${id}`, data);
    },
    getBot: async (id: number) => {
        return api.get(`/dashboard/${id}`);
    },
    deleteBot: async (id: number) => {
        return api.delete(`/dashboard/${id}`);
    },
    getBots: async () => {
        return api.get('/dashboard/');
    },
    getAnalytics: async () => {
        return api.get('/dashboard/analytics/summary');
    },
    getConversations: async (params?: { status?: string; q?: string; days_ago?: number; skip?: number; limit?: number }) => {
        const query = new URLSearchParams();
        if (params?.status) query.set('status', params.status);
        if (params?.q) query.set('q', params.q);
        if (params?.days_ago !== undefined) query.set('days_ago', String(params.days_ago));
        if (params?.skip !== undefined) query.set('skip', String(params.skip));
        if (params?.limit !== undefined) query.set('limit', String(params.limit));
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/dashboard/conversations${suffix}`);
    },
    createConversation: async (botId: number) => {
        return api.post('/dashboard/conversations', { bot_id: botId });
    },
    clearBotConversations: async (botId: number) => {
        return api.delete(`/dashboard/bots/${botId}/conversations`);
    },
    getConversationMessages: async (id: number) => {
        return api.get(`/dashboard/conversations/${id}/messages`);
    },
    chat: async (message: string, conversationId?: number, botId?: number) => {
        return api.post('/chat/', { message, conversation_id: conversationId, bot_id: botId });
    },
    sendAgentMessage: async (conversationId: number, message: string) => {
        return api.post(`/chat/conversations/${conversationId}/messages`, { message });
    },
    getChatHistory: async (botId: number) => {
        return api.get(`/chat/history?bot_id=${botId}`);
    },
    getDocuments: async () => {
        return api.get('/ingest/');
    },
    getCrawlAuditSummary: async () => {
        return api.get('/ingest/audit/summary');
    },
    runAuditTest: async (data: { bot_id: number; question: string; expected_keyword?: string }) => {
        return api.post('/ingest/audit/test-runner', data);
    },
    uploadDocument: async (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/ingest/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        });
    },
    deleteDocument: async (id: number) => {
        return api.delete(`/ingest/${id}`);
    },
    scrapeWebsite: async (url: string, options?: { max_pages?: number; use_sitemaps?: boolean; index_sections?: boolean }) => {
        return api.post('/ingest/scrape', {
            url,
            max_pages: options?.max_pages,
            use_sitemaps: options?.use_sitemaps,
            index_sections: options?.index_sections,
        });
    },
    getBotPublic: async (botId: number) => {
        return api.get(`/dashboard/public/${botId}`);
    },
    chatPublic: async (message: string, botId: number, conversationId?: number) => {
        return api.post('/chat/public', { message, bot_id: botId, conversation_id: conversationId });
    },
    getSettings: async () => {
        return api.get('/dashboard/settings');
    },
    getDashboardRateLimits: async (windowHours: number = 24) => {
        return api.get(`/dashboard/rate-limits?window_hours=${windowHours}`);
    },
    // Leads API
    getLeadForm: async (botId: number) => {
        return api.get(`/leads/forms/${botId}/admin`);
    },
    getLeadFormPublic: async (botId: number) => {
        return api.get(`/leads/forms/${botId}`);
    },
    createLeadForm: async (data: { bot_id: number; title: string; fields: any[] }) => {
        return api.post('/leads/forms', data);
    },
    submitLead: async (botId: number, conversationId: number, data: any, country?: string, source: string = 'Direct') => {
        return api.post('/leads/submit', {
            bot_id: botId,
            conversation_id: conversationId,
            data,
            country,
            source
        });
    },
    getLeads: async () => {
        return api.get('/leads/leads');
    },
    getEmailSettings: async () => {
        return api.get('/leads/email-settings');
    },
    updateEmailSettings: async (data: any) => {
        return api.post('/leads/email-settings', data);
    },
    // Billing API
    createCheckout: async (plan: string) => {
        return api.post('/billing/checkout', { plan });
    },
    // Analytics API
    getAnalyticsSummary: async (days: number = 7) => {
        return api.get(`/analytics/summary?days=${days}`);
    },
    getAnalyticsTrends: async (days: number = 7) => {
        return api.get(`/analytics/trends?days=${days}`);
    },
    getBotPerformance: async (days: number = 7) => {
        return api.get(`/analytics/bot-performance?days=${days}`);
    },
    getRateLimitSummary: async (windowHours: number = 24) => {
        return api.get(`/analytics/rate-limits/summary?window_hours=${windowHours}`);
    },
    getRateLimitPolicies: async (params?: { tenant_filter?: string; plan?: string; route_key?: string }) => {
        const query = new URLSearchParams();
        if (params?.tenant_filter) query.set('tenant_filter', params.tenant_filter);
        if (params?.plan) query.set('plan', params.plan);
        if (params?.route_key) query.set('route_key', params.route_key);
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/admin/rate-limits/policies${suffix}`);
    },
    createRateLimitPolicy: async (data: { tenant_id?: string | null; plan?: 'starter' | 'pro' | 'enterprise' | null; route_key: string; rpm_limit: number; is_active?: boolean }) => {
        return api.post('/admin/rate-limits/policies', data);
    },
    updateRateLimitPolicy: async (policyId: number, data: { tenant_id?: string | null; plan?: 'starter' | 'pro' | 'enterprise' | null; route_key: string; rpm_limit: number; is_active?: boolean }) => {
        return api.put(`/admin/rate-limits/policies/${policyId}`, data);
    },
    deleteRateLimitPolicy: async (policyId: number) => {
        return api.delete(`/admin/rate-limits/policies/${policyId}`);
    },
    getRateLimitAlerts: async (params?: { window_hours?: number; min_hits?: number }) => {
        const query = new URLSearchParams();
        if (params?.window_hours !== undefined) query.set('window_hours', String(params.window_hours));
        if (params?.min_hits !== undefined) query.set('min_hits', String(params.min_hits));
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/admin/rate-limits/alerts${suffix}`);
    },
    getRateLimitNotificationSettings: async () => {
        return api.get('/admin/rate-limits/notifications');
    },
    updateRateLimitNotificationSettings: async (data: {
        rate_limit_email_enabled: boolean;
        rate_limit_email_recipient?: string | null;
        rate_limit_webhook_enabled: boolean;
        rate_limit_webhook_url?: string | null;
        rate_limit_min_hits: number;
        rate_limit_window_minutes: number;
        rate_limit_cooldown_minutes: number;
    }) => {
        return api.put('/admin/rate-limits/notifications', data);
    },
    getRateLimitDeliveries: async (params?: { tenant_filter?: string; route_key?: string; channel?: string; offset?: number; limit?: number }) => {
        const query = new URLSearchParams();
        if (params?.tenant_filter) query.set('tenant_filter', params.tenant_filter);
        if (params?.route_key) query.set('route_key', params.route_key);
        if (params?.channel) query.set('channel', params.channel);
        if (params?.offset !== undefined) query.set('offset', String(params.offset));
        if (params?.limit !== undefined) query.set('limit', String(params.limit));
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/admin/rate-limits/deliveries${suffix}`);
    },
    getRateLimitAudit: async (params?: { action?: string; target_type?: string; offset?: number; limit?: number }) => {
        const query = new URLSearchParams();
        if (params?.action) query.set('action', params.action);
        if (params?.target_type) query.set('target_type', params.target_type);
        if (params?.offset !== undefined) query.set('offset', String(params.offset));
        if (params?.limit !== undefined) query.set('limit', String(params.limit));
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/admin/rate-limits/audit${suffix}`);
    },
    // FAQ / AI Training API
    getBotFAQs: async (botId: number) => {
        return api.get(`/dashboard/${botId}/faqs`);
    },
    createBotFAQ: async (botId: number, data: any) => {
        return api.post(`/dashboard/${botId}/faqs`, data);
    },
    updateBotFAQ: async (botId: number, faqId: number, data: any) => {
        return api.put(`/dashboard/${botId}/faqs/${faqId}`, data);
    },
    deleteBotFAQ: async (botId: number, faqId: number) => {
        return api.delete(`/dashboard/${botId}/faqs/${faqId}`);
    },
    getAIPerformance: async (botId?: number, days: number = 7) => {
        const query = new URLSearchParams();
        if (botId) query.set('bot_id', String(botId));
        query.set('days', String(days));
        return api.get(`/analytics/ai-performance?${query.toString()}`);
    },
    getFaqSuggestions: async (botId?: number, limit: number = 10) => {
        const params = new URLSearchParams();
        if (botId) params.set('bot_id', String(botId));
        params.set('limit', String(limit));
        return api.get(`/analytics/faq-suggestions?${params.toString()}`);
    },
    getCustomersRealtime: async (params?: { status?: string; bot_id?: number; q?: string; limit?: number; offset?: number }) => {
        const query = new URLSearchParams();
        if (params?.status) query.set('status', params.status);
        if (params?.bot_id !== undefined) query.set('bot_id', String(params.bot_id));
        if (params?.q) query.set('q', params.q);
        if (params?.limit !== undefined) query.set('limit', String(params.limit));
        if (params?.offset !== undefined) query.set('offset', String(params.offset));
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return api.get(`/analytics/customers/realtime${suffix}`);
    },
    // Story Builder / Flows API
    getFlows: async (botId: number) => {
        return api.get(`/flows/${botId}/flows`);
    },
    createFlow: async (botId: number, data: { name: string; description?: string; flow_data: any; is_active?: boolean }) => {
        return api.post(`/flows/${botId}/flows`, data);
    },
    updateFlow: async (botId: number, flowId: number, data: { name: string; description?: string; flow_data: any; is_active?: boolean }) => {
        return api.put(`/flows/${botId}/flows/${flowId}`, data);
    },
    deleteFlow: async (botId: number, flowId: number) => {
        return api.delete(`/flows/${botId}/flows/${flowId}`);
    },
    // Agent Transfer Rules API
    getTransferRules: async (botId: number) => {
        return api.get(`/agent-transfer/bots/${botId}/rules`);
    },
    createTransferRule: async (botId: number, data: any) => {
        return api.post(`/agent-transfer/bots/${botId}/rules`, data);
    },
    updateTransferRule: async (botId: number, ruleId: number, data: any) => {
        return api.put(`/agent-transfer/bots/${botId}/rules/${ruleId}`, data);
    },
    deleteTransferRule: async (botId: number, ruleId: number) => {
        return api.delete(`/agent-transfer/bots/${botId}/rules/${ruleId}`);
    },
    triggerManualTransfer: async (conversationId: number, data?: { rule_id?: number; note?: string }) => {
        return api.post(`/agent-transfer/conversations/${conversationId}/trigger`, data || {});
    },
    // Integrations API
    getIntegrations: async (botId: number) => {
        return api.get(`/integrations/bots/${botId}/integrations`);
    },
    upsertIntegration: async (botId: number, data: { integration_type: string; config: any; is_active?: boolean }) => {
        return api.post(`/integrations/bots/${botId}/integrations`, data);
    },
    shopifyOrderLookup: async (botId: number, data: { order_name: string; email?: string }) => {
        return api.post(`/integrations/bots/${botId}/shopify/order-lookup`, data);
    },
    deleteIntegration: async (botId: number, integrationType: string) => {
        return api.delete(`/integrations/bots/${botId}/integrations/${integrationType}`);
    },
    // Quality Command Center API
    getQualityRole: async () => {
        return api.get('/quality/rbac/me');
    },
    getQualityServices: async () => {
        return api.get('/quality/status/services');
    },
    runQualityTests: async (data?: { full?: boolean; include_security_lane?: boolean; parallel?: boolean; max_fail?: number }) => {
        return api.post('/quality/tests/run', data || { full: true, include_security_lane: true, parallel: false, max_fail: 0 });
    },
    getQualityLatest: async () => {
        return api.get('/quality/tests/latest');
    },
    getQualityModules: async () => {
        return api.get('/quality/tests/modules');
    },
    getQualityTrends: async (points: number = 20) => {
        return api.get(`/quality/tests/trends?points=${points}`);
    },
    getQualityFlaky: async () => {
        return api.get('/quality/tests/flaky');
    },
    getQualityCoverage: async () => {
        return api.get('/quality/tests/coverage');
    },
    getObservabilityMetrics: async () => {
        return api.get('/quality/observability/metrics');
    },
    getObservabilityLogs: async (params?: { level?: string; service?: string; limit?: number }) => {
        const q = new URLSearchParams();
        if (params?.level) q.set('level', params.level);
        if (params?.service) q.set('service', params.service);
        if (params?.limit) q.set('limit', String(params.limit));
        const suffix = q.toString() ? `?${q.toString()}` : '';
        return api.get(`/quality/observability/logs${suffix}`);
    },
    getObservabilityTraces: async (limit: number = 30) => {
        return api.get(`/quality/observability/traces?limit=${limit}`);
    },
    getObservabilityAlerts: async () => {
        return api.get('/quality/observability/alerts');
    },
    getReleaseChecklist: async () => {
        return api.get('/quality/release/checklist');
    },
    updateReleaseChecklist: async (data: any) => {
        return api.put('/quality/release/checklist', data);
    },
    getReleaseRisk: async () => {
        return api.get('/quality/release/risk');
    },
    exportReleaseEvidence: async () => {
        return api.get('/quality/release/evidence');
    },
    applyQualityRetention: async (days: number) => {
        return api.post(`/quality/retention/apply?days=${days}`);
    },
    getSecurityChecklist: async () => {
        return api.get('/quality/security/checklist');
    },
    // Admin Tenant & Plan Management
    getAdminTenants: async () => {
        return api.get('/admin/tenants');
    },
    createTenant: async (data: { name: string; id: string; plan: string }) => {
        return api.post('/admin/tenants', data);
    },
    updateTenantPlan: async (tenantId: string, plan: string) => {
        return api.put(`/admin/tenants/${tenantId}/plan`, { plan });
    },
    getAdminPlans: async () => {
        return api.get('/admin/plans');
    },
    updatePlanLimits: async (planName: string, data: { message_limit: number; document_limit: number; bot_limit: number }) => {
        return api.put(`/admin/plans/${planName}`, data);
    }
};
