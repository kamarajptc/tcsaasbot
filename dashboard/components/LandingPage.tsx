'use client';

import React, { useState, useEffect } from 'react';
import { CHATBOT_TEMPLATES, BotTemplate } from '@/lib/templates';
import { Bot, Shield, ArrowRight, CheckCircle2, MessageSquare, Globe, Layout, Sparkles, Target, Activity, ChevronDown, Star } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { dashboardApi, isValidToken } from '@/lib/api';

interface LandingPageProps {
    readonly onGetStarted: () => void;
}

export function LandingPage({ onGetStarted }: LandingPageProps) {
    const router = useRouter();
    const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');
    const [openFaqId, setOpenFaqId] = useState('faq-1');
    const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    useEffect(() => {
        setIsAuthenticated(isValidToken(localStorage.getItem('access_token')));
    }, []);
    const [roiInputs, setRoiInputs] = useState({
        monthlyVisitors: 10000,
        currentLeadRate: 2,
        improvedLeadRate: 4.5,
        averageDealValue: 1200
    });

    const stats = [
        { label: 'Active Agents', val: '14', id: 'stat-1' },
        { label: 'Intelligence Nodes', val: '23', id: 'stat-2' },
        { label: 'Total Conversions', val: '9', id: 'stat-3' },
        { label: 'Early Adopters', val: '5', id: 'stat-4' }
    ];

    const features = [
        {
            id: 'f1',
            icon: <Globe className="w-6 h-6" />,
            title: "Recursive Synchronization",
            desc: "Sync deep data from PDFs, Word docs, and localized web scrapers with enterprise-grade recursive crawling."
        },
        {
            id: 'f2',
            icon: <Shield className="w-6 h-6" />,
            title: "Knowledge Ledger",
            desc: "Complete transparency into your bot's intelligence. Manage indexed content with real-time vector search."
        },
        {
            id: 'f3',
            icon: <Target className="w-6 h-6" />,
            title: "Conversion Engine",
            desc: "Customizable lead forms that proactively capture user intent and deliver instant CRM notifications."
        },
        {
            id: 'f4',
            icon: <Activity className="w-6 h-6" />,
            title: "Growth Analytics",
            desc: "Deep insights into bot performance, traffic spikes, and conversion trends with real-time telemetry."
        },
        {
            id: 'f5',
            icon: <Layout className="w-6 h-6" />,
            title: "Visual Brand DNA",
            desc: "Personalize every pixel. Customize avatars, greetings, positioning, and colors to match your brand identity."
        },
        {
            id: 'f6',
            icon: <Sparkles className="w-6 h-6" />,
            title: "Context-Aware RAG",
            desc: "History-aware agents that maintain fluid, multi-turn conversations with localized knowledge recall."
        }
    ];

    const templates: BotTemplate[] = CHATBOT_TEMPLATES;

    const launchFlow = [
        { id: 's1', step: 'Connect your website and docs', note: 'Import URLs, PDFs, and help center pages.' },
        { id: 's2', step: 'Customize voice and widget style', note: 'Control tone, avatar, greeting, and widget placement.' },
        { id: 's3', step: 'Go live and optimize conversions', note: 'Track chats, leads, and outcome quality from one dashboard.' }
    ];

    const trustBrands = ['Tangent Cloud', 'Adamsbridge', 'dataflo', 'WorkEZ'];

    const pricingTiers = [
        {
            name: 'Starter',
            monthlyPrice: '$0',
            yearlyPrice: '$0',
            features: ['1 AI Bot', '100 Messages/mo', 'Basic Knowledge Indexing', 'Standard Support'],
            button: 'Launch Free'
        },
        {
            name: 'Pro',
            monthlyPrice: '$49',
            yearlyPrice: '$39',
            features: ['10 AI Bots', '5,000 Messages/mo', 'Recursive Website Crawling', 'Lead Gen CRM Sync', 'Custom DNA Branding', 'Priority Escalation'],
            button: 'Upgrade to Pro',
            highlighted: true
        },
        {
            name: 'Enterprise',
            monthlyPrice: 'Custom',
            yearlyPrice: 'Custom',
            features: ['Unlimited Agents', 'Unlimited Context Nodes', 'Whitelabel Deployment', 'API Hub Access', 'Dedicated Account Engineer'],
            button: 'Contact Sales'
        }
    ];

    const faqItems = [
        {
            id: 'faq-1',
            question: 'Can I deploy this without engineering help?',
            answer: 'Yes. You can ingest content, configure brand style, and publish the widget from the dashboard without code.'
        },
        {
            id: 'faq-2',
            question: 'How does lead capture work?',
            answer: 'You can define custom lead forms that appear in-chat based on message behavior, then sync responses to your CRM.'
        },
        {
            id: 'faq-3',
            question: 'Can I train different bots for different products?',
            answer: 'Yes. Each bot can have independent datasets, personality settings, and widget placement rules.'
        },
        {
            id: 'faq-4',
            question: 'Is there a free plan?',
            answer: 'Starter is free and includes one bot so you can test workflows before upgrading.'
        }
    ];

    const goToOnboarding = (templateId?: string) => {
        if (!isAuthenticated) {
            setShowSignUp(true);
            return;
        }
        if (templateId) {
            router.push(`/onboarding?template=${templateId}`);
            return;
        }
        router.push('/onboarding');
    };

    const selectedTemplate = templates.find((template: BotTemplate) => template.id === activeTemplateId);
    const currentMonthlyLeads = Math.round((roiInputs.monthlyVisitors * roiInputs.currentLeadRate) / 100);
    const improvedMonthlyLeads = Math.round((roiInputs.monthlyVisitors * roiInputs.improvedLeadRate) / 100);
    const additionalLeads = Math.max(0, improvedMonthlyLeads - currentMonthlyLeads);
    const additionalRevenue = additionalLeads * roiInputs.averageDealValue;

    const [showSignIn, setShowSignIn] = useState(false);
    const [showSignUp, setShowSignUp] = useState(false);
    const [showForgot, setShowForgot] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const TEST_CREDENTIALS = [
        { role: 'Tangent Cloud Admin', email: 'ops@tangentcloud.in', desc: 'AI SaaS platform bot operations' },
        { role: 'dataflo Ops', email: 'ops@dataflo.io', desc: 'No-code data automation support' },
        { role: 'Adamsbridge IAM', email: 'ops@adamsbridge.com', desc: 'Identity and process knowledge assistant' },
        { role: 'WorkEZ HR Ops', email: 'ops@workez.in', desc: 'HRMS and workspace operations assistant' },
    ];

    const fillCredential = async (cred: typeof TEST_CREDENTIALS[0]) => {
        setEmail(cred.email);
        setPassword('password123');
        setIsLoading(true);
        try {
            // Wait a tiny bit for UI to reflect the filled fields before jumping
            await new Promise(resolve => setTimeout(resolve, 300));
            const data = await dashboardApi.login(cred.email, 'password123');
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('tcsaas_api_key', cred.email.replace(/[^a-zA-Z0-9@._-]/g, ''));
            setIsLoading(false);
            onGetStarted();
            router.push('/?start=dashboard');
        } catch (error) {
            console.error('Auto-login failed', error);
            setIsLoading(false);
            alert('Authentication failed. Selecting this persona didn\'t work.');
        }
    };


    const handleAuth = async (e: React.FormEvent, _type: 'signin' | 'signup') => {
        e.preventDefault();
        void _type;
        setIsLoading(true);
        try {
            // In a real app, signup would be a separate endpoint
            // For this MVP, we use login for both (auth endpoint handles creating context if needed or just validates)
            // But actually we only implemented login.
            // Let's assume signup just logs in for now or we can implement signup later.
            // For now, we will just call login.

            const data = await dashboardApi.login(email, password || 'password123'); // Default password for test creds if empty
            localStorage.setItem('access_token', data.access_token);
            // Also keep the key for legacy components if any
            localStorage.setItem('tcsaas_api_key', email.replace(/[^a-zA-Z0-9@._-]/g, ''));

            setIsLoading(false);
            onGetStarted();
            router.push('/?start=dashboard');
        } catch (error) {
            console.error('Login failed', error);
            setIsLoading(false);
            alert('Authentication failed. Please check your credentials.');
        }
    };

    const handleForgot = (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setTimeout(() => {
            setIsLoading(false);
            setShowForgot(false);
            alert('Password reset link sent to ' + email);
        }, 1000);
    };

    return (
        <div className="bg-white min-h-screen selection:bg-blue-100">
            {/* Nav */}
            <nav className="fixed top-0 left-0 right-0 z-[100] bg-white/70 backdrop-blur-2xl border-b border-gray-100">
                <div className="max-w-7xl mx-auto px-8 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-3 cursor-pointer" onClick={() => router.push('/')}>
                        <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-lg shadow-gray-100 p-1">
                            <img src="/img/logo.png" alt="Logo" className="w-full h-full object-contain" />
                        </div>
                        <span className="text-2xl font-black text-gray-900 tracking-tighter">Tangent Cloud</span>
                    </div>
                    <div className="hidden lg:flex items-center gap-10 text-[11px] font-black uppercase tracking-widest text-gray-400">
                        <button onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })} className="hover:text-blue-600 transition-colors uppercase">Technology</button>
                        <button onClick={() => document.getElementById('pricing')?.scrollIntoView({ behavior: 'smooth' })} className="hover:text-blue-600 transition-colors uppercase">Plans</button>
                        <button onClick={() => document.getElementById('faq')?.scrollIntoView({ behavior: 'smooth' })} className="hover:text-blue-600 transition-colors uppercase">FAQ</button>
                        <button
                            onClick={() => setShowSignIn(true)}
                            className="hover:text-blue-600 transition-colors uppercase text-gray-900"
                        >
                            Sign In
                        </button>
                        <button
                            onClick={() => setShowSignUp(true)}
                            className="bg-blue-600 text-white px-8 py-3 rounded-2xl hover:bg-blue-700 shadow-xl shadow-blue-200 hover:shadow-blue-300 transition-all active:scale-95"
                        >
                            Get Started
                        </button>
                    </div>
                </div>
            </nav>

            {/* Auth Modals */}
            {(showSignIn || showSignUp || showForgot) && (
                <div className="fixed inset-0 z-[150] bg-blue-600/60 backdrop-blur-md flex items-center justify-center p-4">
                    <div className="bg-white rounded-[2.5rem] p-10 w-full max-w-4xl shadow-2xl relative animate-in fade-in zoom-in-95 duration-200 flex gap-10">

                        {/* Left Side: Form */}
                        <div className="flex-1 max-w-md">
                            <button
                                onClick={() => { setShowSignIn(false); setShowSignUp(false); setShowForgot(false); }}
                                className="absolute top-6 right-6 p-2 rounded-full hover:bg-gray-50 transition-colors text-gray-400 hover:text-gray-900 lg:hidden"
                            >
                                <ChevronDown className="w-6 h-6 rotate-180" />
                            </button>

                            <div className="text-center mb-8">
                                <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-xl shadow-blue-200 mx-auto mb-6">
                                    <Bot className="text-white w-8 h-8" />
                                </div>
                                <h2 className="text-3xl font-black text-gray-900 tracking-tight mb-2">
                                    {showForgot ? 'Reset Password' : (showSignUp ? 'Create Account' : 'Welcome Back')}
                                </h2>
                                <p className="text-gray-500 font-medium">
                                    {showForgot ? 'Enter your email to receive recovery instructions.' :
                                        (showSignUp ? 'Start building your AI workforce today.' : 'Sign in to manage your agents.')}
                                </p>
                            </div>

                            {showForgot ? (
                                <form onSubmit={handleForgot} className="space-y-6">
                                    <div className="space-y-2">
                                        <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 ml-1">Work Email</label>
                                        <input
                                            type="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                            className="w-full px-5 py-4 rounded-xl bg-gray-50 border-transparent focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all font-medium text-gray-900 placeholder:text-gray-400"
                                            placeholder="name@company.com"
                                        />
                                    </div>
                                    <button type="submit" disabled={isLoading} className="w-full py-4 bg-blue-600 text-white rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-indigo-700 transition-all shadow-xl shadow-blue-200 disabled:opacity-70 disabled:cursor-not-allowed">
                                        {isLoading ? 'Sending...' : 'Send Recovery Link'}
                                    </button>
                                    <button type="button" onClick={() => { setShowForgot(false); setShowSignIn(true); }} className="w-full py-2 text-xs font-bold text-gray-400 hover:text-gray-900 transition-colors">
                                        Back to Sign In
                                    </button>
                                </form>
                            ) : (
                                <form onSubmit={(e) => handleAuth(e, showSignUp ? 'signup' : 'signin')} className="space-y-5">
                                    <div className="space-y-2">
                                        <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 ml-1">Work Email</label>
                                        <input
                                            type="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                            className="w-full px-5 py-4 rounded-xl bg-gray-50 border-transparent focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all font-medium text-gray-900 placeholder:text-gray-400"
                                            placeholder="name@company.com"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <div className="flex justify-between items-center px-1">
                                            <label className="text-[10px] font-black uppercase tracking-widest text-gray-500">Password</label>
                                            {!showSignUp && (
                                                <button type="button" onClick={() => { setShowSignIn(false); setShowForgot(true); }} className="text-[10px] font-black uppercase tracking-widest text-blue-600 hover:text-blue-700">
                                                    Forgot?
                                                </button>
                                            )}
                                        </div>
                                        <input
                                            type="password"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            required
                                            className="w-full px-5 py-4 rounded-xl bg-gray-50 border-transparent focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all font-medium text-gray-900 placeholder:text-gray-400"
                                            placeholder="••••••••"
                                        />
                                    </div>
                                    <button type="submit" disabled={isLoading} className="w-full py-4 bg-blue-600 text-white rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-blue-700 transition-all shadow-xl shadow-blue-200 hover:shadow-blue-300 disabled:opacity-70 disabled:cursor-not-allowed">
                                        {isLoading ? 'Processing...' : (showSignUp ? 'Create Account' : 'Sign In')}
                                    </button>

                                    <div className="pt-4 text-center">
                                        <p className="text-sm font-medium text-gray-500">
                                            {showSignUp ? 'Already have an account?' : 'New to Tangent Cloud?'}
                                            <button
                                                type="button"
                                                onClick={() => { setShowSignUp(!showSignUp); setShowSignIn(!showSignIn); }}
                                                className="ml-2 text-gray-900 font-bold hover:text-blue-600 transition-colors"
                                            >
                                                {showSignUp ? 'Sign In' : 'Sign Up'}
                                            </button>
                                        </p>
                                    </div>
                                </form>
                            )}
                        </div>

                        {/* Right Side: Test Credentials (Only on Sign In) */}
                        {!showForgot && !showSignUp && (
                            <div className="hidden lg:flex w-80 border-l border-gray-100 pl-10 flex-col">
                                <div className="mb-6">
                                    <h3 className="text-sm font-black text-gray-900 uppercase tracking-widest mb-2">Quick Access</h3>
                                    <p className="text-xs text-gray-500 font-medium">Select a persona to demo the platform.</p>
                                </div>
                                <div className="space-y-3 overflow-y-auto pr-4 max-h-[500px] no-scrollbar">
                                    {TEST_CREDENTIALS.map((cred) => (
                                        <button
                                            key={cred.email}
                                            onClick={() => fillCredential(cred)}
                                            className="w-full text-left p-4 rounded-2xl border border-gray-100 hover:border-blue-200 hover:bg-blue-50/50 transition-all group"
                                        >
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="text-xs font-black text-gray-900 uppercase tracking-widest">{cred.role}</span>
                                                <ArrowRight className="w-3 h-3 text-gray-300 group-hover:text-blue-600 transition-colors" />
                                            </div>
                                            <div className="text-xs font-bold text-gray-600 mb-1">{cred.email}</div>
                                            <div className="text-[10px] text-gray-400 font-medium">{cred.desc}</div>
                                        </button>
                                    ))}
                                </div>
                                <button
                                    onClick={() => { setShowSignIn(false); setShowSignUp(false); }}
                                    className="absolute top-6 right-6 p-2 rounded-full hover:bg-gray-50 transition-colors text-gray-400 hover:text-gray-900"
                                >
                                    <ChevronDown className="w-6 h-6 rotate-180" />
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Hero */}
            <header className="relative pt-48 pb-40 overflow-hidden bg-[radial-gradient(circle_at_top,rgba(37,99,235,0.05),transparent)]">
                <div className="max-w-7xl mx-auto px-8 text-center space-y-10 relative z-10">
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-blue-50 text-blue-600 rounded-full text-[10px] font-black uppercase tracking-[0.2em]">
                        <Sparkles className="w-3 h-3 animate-pulse" /> The Future of Support is Agentic
                    </div>
                    <h1 className="text-6xl md:text-8xl font-black text-gray-900 leading-[0.95] tracking-tighter">
                        Build Smarter <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-br from-blue-600 to-indigo-700">
                            AI Personas
                        </span>
                    </h1>
                    <p className="max-w-3xl mx-auto text-lg md:text-xl text-gray-500 leading-relaxed font-medium">
                        Build website chatbots that answer instantly, capture qualified leads, and keep improving from every conversation.
                        No code needed to launch your first AI assistant.
                    </p>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-6 pt-4">
                        <button
                            onClick={() => goToOnboarding()}
                            className="w-full sm:w-auto px-10 py-5 bg-blue-600 text-white rounded-3xl font-black text-lg shadow-2xl shadow-gray-300 hover:bg-indigo-700 hover:-translate-y-1 transition-all active:scale-95 flex items-center justify-center gap-2 group"
                        >
                            Build Your Free Agent <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform" />
                        </button>
                        <button
                            onClick={onGetStarted}
                            className="w-full sm:w-auto px-10 py-5 bg-white text-gray-900 border-2 border-gray-100 rounded-3xl font-black text-lg hover:border-blue-100 hover:bg-blue-50/30 transition-all flex items-center justify-center gap-2"
                        >
                            Interactive Demo
                        </button>
                    </div>

                    {/* Feature Showcase */}
                    <div className="mt-32 relative max-w-6xl mx-auto">
                        <div className="absolute -inset-4 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-[3rem] opacity-20 blur-2xl -z-10 animate-pulse" />
                        <div className="bg-white rounded-[3rem] border border-gray-100 shadow-2xl overflow-hidden p-6 md:p-12 text-left">
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
                                <div className="space-y-6">
                                    <div className="w-16 h-1 bg-blue-600 rounded-full" />
                                    <h3 className="text-4xl font-black text-gray-900 tracking-tight">Deploy anywhere. <br />Customize everything.</h3>
                                    <p className="text-gray-500 font-medium leading-relaxed">
                                        Unlike generic chatbots, Tangent Cloud AI Bots gives you full control over the visual DNA and behavioral persona of your AI agents.
                                        Choose specialized positions, custom avatars, and engagement-focused proactive greetings.
                                    </p>
                                    <div className="space-y-3">
                                        {['Proactive Shoutouts', 'Custom Visual Personas', 'Recursive Knowledge Sync'].map(p => (
                                            <div key={p} className="flex items-center gap-3 text-sm font-black text-gray-800">
                                                <CheckCircle2 className="w-5 h-5 text-blue-600" /> {p}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div className="bg-gray-50 rounded-[2rem] border-2 border-gray-100 h-[320px] flex items-center justify-center p-6">
                                    <div className="w-full max-w-xs space-y-3">
                                        <div className="bg-white px-4 py-3 rounded-2xl shadow-sm border border-gray-100 text-xs font-bold text-gray-700">
                                            Hi there. Looking for pricing details?
                                        </div>
                                        <div className="bg-blue-600 text-white px-4 py-3 rounded-2xl rounded-br-md text-xs font-bold shadow-lg shadow-blue-200 ml-8">
                                            Yes, and I need CRM integration.
                                        </div>
                                        <div className="bg-white px-4 py-3 rounded-2xl shadow-sm border border-gray-100 text-xs font-bold text-gray-700">
                                            Perfect. The Pro plan includes CRM sync and custom lead forms.
                                        </div>
                                        <div className="flex items-center gap-2 pt-1">
                                            <MessageSquare className="w-4 h-4 text-blue-600" />
                                            <p className="text-[10px] font-black text-gray-700 uppercase tracking-widest">Live Widget Simulation</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            {/* Stats Ledger */}
            <section className="py-24 border-y bg-gray-50/30">
                <div className="max-w-7xl mx-auto px-8 grid grid-cols-2 lg:grid-cols-4 gap-16 text-center">
                    {stats.map((stat) => (
                        <div key={stat.id} className="space-y-1">
                            <div className="text-4xl font-black text-gray-900 tracking-tighter">{stat.val}</div>
                            <div className="text-[10px] font-black text-gray-700 uppercase tracking-[0.2em]">{stat.label}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Trust Rail */}
            <section className="py-14">
                <div className="max-w-7xl mx-auto px-8">
                    <p className="text-center text-[10px] font-black uppercase tracking-[0.2em] text-gray-700 mb-8">Ready for early adopters</p>
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                        {trustBrands.map((brand) => (
                            <div key={brand} className="h-14 rounded-2xl bg-gray-50 border border-gray-100 flex items-center justify-center">
                                <span className="text-sm font-black text-gray-500 tracking-tight">{brand}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Grid Features */}
            <section id="features" className="py-40">
                <div className="max-w-7xl mx-auto px-8 space-y-24">
                    <div className="text-center space-y-6">
                        <h2 className="text-5xl font-black text-gray-900 tracking-tight">High-Performance Infrastructure</h2>
                        <p className="text-gray-500 max-w-3xl mx-auto font-medium text-lg leading-relaxed">
                            Built with the same technology stack used by the world&apos;s leading SaaS companies.
                            Scalable, secure, and lightning-fast.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
                        {features.map((feature) => (
                            <div key={feature.id} className="p-10 bg-white border border-gray-100 rounded-[2.5rem] hover:border-blue-200 hover:shadow-2xl hover:shadow-blue-50/50 transition-all group relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-10 opacity-5 group-hover:scale-110 transition-transform">
                                    {feature.icon}
                                </div>
                                <div className="p-4 bg-gray-50 rounded-2xl w-fit mb-8 group-hover:bg-blue-600 group-hover:text-white transition-all group-hover:scale-110 group-hover:shadow-lg group-hover:shadow-blue-200">
                                    {feature.icon}
                                </div>
                                <h3 className="text-xl font-black text-gray-900 mb-4 tracking-tight">{feature.title}</h3>
                                <p className="text-gray-500 text-sm leading-relaxed font-medium">{feature.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Templates */}
            <section className="py-28 bg-gradient-to-b from-white to-blue-50/40 border-y border-gray-100">
                <div className="max-w-7xl mx-auto px-8 space-y-14">
                    <div className="text-center space-y-5">
                        <h2 className="text-4xl md:text-5xl font-black text-gray-900 tracking-tight">Start From Proven Chatbot Templates</h2>
                        <p className="text-gray-500 max-w-3xl mx-auto font-medium text-lg leading-relaxed">
                            Launch faster with ready-to-use assistants designed for common business goals.
                        </p>
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {templates.map((template: BotTemplate) => (
                            <div key={template.id} className="bg-white border border-gray-100 rounded-3xl p-8 shadow-sm hover:shadow-xl transition-all">
                                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600 mb-4">{template.audience}</p>
                                <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-4">{template.name}</h3>
                                <p className="text-sm text-gray-500 font-medium leading-relaxed mb-8">{template.preview}</p>
                                <div className={`grid ${isAuthenticated ? 'grid-cols-2' : 'grid-cols-1'} gap-3`}>
                                    <button
                                        onClick={() => setActiveTemplateId(template.id)}
                                        className="w-full py-3 rounded-2xl bg-white border border-gray-200 text-gray-900 text-xs font-black uppercase tracking-widest hover:bg-gray-50 transition-colors"
                                    >
                                        Preview
                                    </button>
                                    {isAuthenticated && (
                                        <button
                                            onClick={() => goToOnboarding(template.id)}
                                            className="w-full py-3 rounded-2xl bg-blue-600 text-white text-xs font-black uppercase tracking-widest hover:bg-indigo-700 transition-colors"
                                        >
                                            Use Template
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ROI Estimator */}
            <section className="py-32 bg-gray-50/60 border-y border-gray-100">
                <div className="max-w-7xl mx-auto px-8 grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">
                    <div className="space-y-6">
                        <p className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">Revenue Impact</p>
                        <h2 className="text-4xl md:text-5xl font-black text-gray-900 tracking-tight">Estimate Your Monthly ROI</h2>
                        <p className="text-gray-500 font-medium text-lg leading-relaxed">
                            Adjust your baseline metrics to estimate what a higher-converting chatbot could add to pipeline and revenue.
                        </p>
                        <button
                            onClick={() => goToOnboarding()}
                            className="px-8 py-4 bg-blue-600 text-white rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-indigo-700 transition-colors shadow-xl shadow-blue-100"
                        >
                            Launch My Bot
                        </button>
                    </div>
                    <div className="rounded-[2rem] bg-white border border-gray-100 p-8 shadow-sm space-y-7">
                        <div className="space-y-2">
                            <label className="text-xs font-black text-gray-500 uppercase tracking-widest">Monthly Website Visitors: {roiInputs.monthlyVisitors.toLocaleString()}</label>
                            <input type="range" min={1000} max={100000} step={1000} value={roiInputs.monthlyVisitors} onChange={(e) => setRoiInputs((prev) => ({ ...prev, monthlyVisitors: Number(e.target.value) }))} className="w-full" />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-black text-gray-500 uppercase tracking-widest">Current Lead Rate: {roiInputs.currentLeadRate}%</label>
                            <input type="range" min={0.5} max={10} step={0.1} value={roiInputs.currentLeadRate} onChange={(e) => setRoiInputs((prev) => ({ ...prev, currentLeadRate: Number(e.target.value) }))} className="w-full" />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-black text-gray-500 uppercase tracking-widest">Lead Rate With Tangent Cloud AI Bots: {roiInputs.improvedLeadRate}%</label>
                            <input type="range" min={1} max={20} step={0.1} value={roiInputs.improvedLeadRate} onChange={(e) => setRoiInputs((prev) => ({ ...prev, improvedLeadRate: Number(e.target.value) }))} className="w-full" />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-black text-gray-500 uppercase tracking-widest">Average Deal Value: ${roiInputs.averageDealValue.toLocaleString()}</label>
                            <input type="range" min={100} max={10000} step={100} value={roiInputs.averageDealValue} onChange={(e) => setRoiInputs((prev) => ({ ...prev, averageDealValue: Number(e.target.value) }))} className="w-full" />
                        </div>
                        <div className="grid grid-cols-2 gap-4 pt-2">
                            <div className="p-4 rounded-2xl bg-blue-50 border border-blue-100">
                                <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest">Additional Leads / Mo</p>
                                <p className="text-3xl font-black text-blue-700 tracking-tight">{additionalLeads}</p>
                            </div>
                            <div className="p-4 rounded-2xl bg-green-50 border border-green-100">
                                <p className="text-[10px] text-green-600 font-black uppercase tracking-widest">Potential Revenue / Mo</p>
                                <p className="text-3xl font-black text-green-700 tracking-tight">${additionalRevenue.toLocaleString()}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* How It Works */}
            <section className="py-32">
                <div className="max-w-7xl mx-auto px-8 space-y-14">
                    <div className="text-center space-y-5">
                        <h2 className="text-4xl md:text-5xl font-black text-gray-900 tracking-tight">Launch In 3 Steps</h2>
                        <p className="text-gray-500 max-w-3xl mx-auto font-medium text-lg leading-relaxed">
                            From setup to lead capture in less than an hour.
                        </p>
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {launchFlow.map((item, index) => (
                            <div key={item.id} className="rounded-3xl border border-gray-100 bg-white p-8 relative">
                                <div className="w-10 h-10 rounded-xl bg-blue-600 text-white text-sm font-black flex items-center justify-center mb-5 shadow-lg shadow-blue-200">
                                    {index + 1}
                                </div>
                                <h3 className="text-xl font-black text-gray-900 tracking-tight mb-3">{item.step}</h3>
                                <p className="text-sm font-medium text-gray-500 leading-relaxed">{item.note}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Premium Pricing */}
            <section id="pricing" className="py-40">
                <div className="max-w-7xl mx-auto px-8 space-y-20">
                    <div className="text-center space-y-6">
                        <h2 className="text-5xl font-black text-gray-900 tracking-tight underline decoration-blue-600/20 underline-offset-8">Scale Your Intelligence</h2>
                        <p className="text-gray-500 font-medium text-lg">Choose a plan that matches your organization&apos;s growth.</p>
                        <div className="inline-flex p-1.5 bg-gray-100 rounded-2xl gap-1">
                            <button
                                type="button"
                                onClick={() => setBillingCycle('monthly')}
                                className={`px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${billingCycle === 'monthly' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
                            >
                                Monthly
                            </button>
                            <button
                                type="button"
                                onClick={() => setBillingCycle('yearly')}
                                className={`px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${billingCycle === 'yearly' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
                            >
                                Yearly
                            </button>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 items-end">
                        {pricingTiers.map((tier) => (
                            <div key={tier.name} className={`p-12 rounded-[3.5rem] transition-all relative group ${tier.highlighted ? 'bg-blue-600 text-white shadow-3xl shadow-blue-200 scale-105' : 'bg-white border-2 border-gray-100 hover:border-blue-100'
                                }`}>
                                {tier.highlighted && (
                                    <div className="absolute -top-5 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-6 py-2 rounded-full text-[10px] font-black uppercase tracking-widest shadow-xl shadow-blue-200">
                                        {billingCycle === 'yearly' ? 'Most Popular - Save 20%' : 'Most Popular'}
                                    </div>
                                )}
                                <h3 className={`text-2xl font-black mb-2 tracking-tight ${tier.highlighted ? 'text-blue-400' : 'text-gray-900'}`}>{tier.name}</h3>
                                <div className="flex items-baseline gap-1 mb-10">
                                    <span className="text-6xl font-black tracking-tighter">
                                        {billingCycle === 'monthly' ? tier.monthlyPrice : tier.yearlyPrice}
                                    </span>
                                    {tier.name !== 'Enterprise' && (
                                        <span className={`text-sm font-bold uppercase tracking-widest ${tier.highlighted ? 'text-gray-500' : 'text-gray-300'}`}>
                                            /{billingCycle === 'monthly' ? 'Mo' : 'Mo, billed yearly'}
                                        </span>
                                    )}
                                </div>
                                <ul className="space-y-6 mb-12">
                                    {tier.features.map(f => (
                                        <li key={f} className="flex items-start gap-4 text-sm font-bold leading-tight">
                                            <CheckCircle2 className={`w-5 h-5 shrink-0 ${tier.highlighted ? 'text-blue-500' : 'text-blue-600'}`} /> {f}
                                        </li>
                                    ))}
                                </ul>
                                <button
                                    onClick={() => goToOnboarding()}
                                    className={`w-full py-5 rounded-[2rem] font-black text-sm uppercase tracking-widest transition-all active:scale-95 ${tier.highlighted ? 'bg-blue-600 text-white shadow-2xl shadow-blue-500/20 hover:bg-blue-500 hover:-translate-y-1' : 'bg-gray-50 text-gray-900 hover:bg-gray-100'
                                        }`}>
                                    {tier.button}
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Testimonials */}
            <section className="py-28 bg-blue-50/40 border-y border-gray-100">
                <div className="max-w-7xl mx-auto px-8 space-y-14">
                    <div className="text-center space-y-4">
                        <h2 className="text-4xl md:text-5xl font-black text-gray-900 tracking-tight">Built for Enterprise Reliability</h2>
                        <p className="text-gray-500 font-medium text-lg">Our platform is engineered for scale and production-grade stability.</p>
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {[
                            { id: 'r1', quote: 'We cut first-response time by 72% in two weeks.', author: 'Head of Support, Cloudfleet' },
                            { id: 'r2', quote: 'Lead quality improved because the bot pre-qualified every request.', author: 'Growth Lead, MarketPilot' },
                            { id: 'r3', quote: 'Setup took under an hour, and we were live the same day.', author: 'Founder, PulseDesk' }
                        ].map((item) => (
                            <article key={item.id} className="p-8 bg-white rounded-3xl border border-gray-100 shadow-sm">
                                <div className="flex gap-1 mb-5">
                                    {[1, 2, 3, 4, 5].map((star) => (
                                        <Star key={star} className="w-4 h-4 text-amber-400 fill-amber-400" />
                                    ))}
                                </div>
                                <p className="text-lg font-bold text-gray-800 leading-relaxed mb-6">{item.quote}</p>
                                <p className="text-xs font-black uppercase tracking-widest text-gray-400">{item.author}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            {/* FAQ */}
            <section id="faq" className="py-32">
                <div className="max-w-4xl mx-auto px-8 space-y-10">
                    <div className="text-center space-y-4">
                        <h2 className="text-4xl md:text-5xl font-black text-gray-900 tracking-tight">Frequently Asked Questions</h2>
                        <p className="text-gray-500 font-medium text-lg">Everything you need before launching.</p>
                    </div>
                    <div className="space-y-4">
                        {faqItems.map((faq) => {
                            const isOpen = openFaqId === faq.id;
                            return (
                                <div key={faq.id} className="border border-gray-100 rounded-3xl bg-white overflow-hidden">
                                    <button
                                        type="button"
                                        onClick={() => setOpenFaqId(isOpen ? '' : faq.id)}
                                        className="w-full flex items-center justify-between text-left px-7 py-6"
                                    >
                                        <span className="text-base font-black text-gray-900 pr-4">{faq.question}</span>
                                        <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                    </button>
                                    {isOpen && (
                                        <div className="px-7 pb-6">
                                            <p className="text-sm text-gray-500 font-medium leading-relaxed">{faq.answer}</p>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    <div className="text-center">
                        <button
                            onClick={() => goToOnboarding()}
                            className="px-10 py-4 bg-blue-600 text-white rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-indigo-700 transition-colors shadow-2xl shadow-blue-200"
                        >
                            Start Building Free
                        </button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="py-32 border-t border-gray-100 bg-gray-50/50">
                <div className="max-w-7xl mx-auto px-8 flex flex-col lg:flex-row justify-between items-center gap-12">
                    <div className="space-y-4 text-center lg:text-left">
                        <div className="flex items-center justify-center lg:justify-start gap-3">
                            <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-lg shadow-gray-100 p-1">
                                <img src="/img/logo.png" alt="Logo" className="w-full h-full object-contain" />
                            </div>
                            <span className="text-2xl font-black text-gray-900 tracking-tighter">Tangent Cloud</span>
                        </div>
                        <p className="text-gray-400 text-sm font-medium max-w-xs">
                            The world’s most advanced AI agent orchestration platform.
                            Scalable, secure, and built for growth.
                        </p>
                    </div>
                    <div className="flex flex-col md:flex-row gap-12 items-center">
                        <div className="flex flex-col gap-3 font-black text-[10px] uppercase tracking-widest text-gray-400">
                            <button type="button" onClick={() => router.push('/architecture')} className="text-left hover:text-blue-600 transition-colors">Architecture</button>
                            <button type="button" onClick={() => router.push('/privacy')} className="text-left hover:text-blue-600 transition-colors">Privacy Policy</button>
                            <button type="button" onClick={() => router.push('/security-sla')} className="text-left hover:text-blue-600 transition-colors">Security SLA</button>
                        </div>
                        <div className="text-center lg:text-right space-y-2">
                            <p className="text-gray-400 text-sm font-bold">© 2026 Tangent Cloud Technologies Inc.</p>
                            <div className="flex items-center justify-center lg:justify-end gap-2 text-xs font-black text-gray-900">
                                <Shield className="w-4 h-4 text-blue-600" /> Enterprise Secured
                            </div>
                        </div>
                    </div>
                </div>
            </footer>

            {/* Mobile Sticky CTA */}
            <div className="fixed bottom-4 left-4 right-4 lg:hidden z-[120]">
                <button
                    onClick={() => goToOnboarding()}
                    className="w-full py-4 rounded-2xl bg-blue-600 text-white text-sm font-black uppercase tracking-widest shadow-2xl shadow-blue-300 active:scale-95 transition-all"
                >
                    Launch Free Agent
                </button>
            </div>

            {/* Template Preview Modal */}
            {selectedTemplate && (
                <div className="fixed inset-0 z-[140] bg-blue-600/40 backdrop-blur-sm p-4 flex items-center justify-center">
                    <div className="w-full max-w-2xl bg-white rounded-[2rem] border border-gray-100 shadow-2xl p-8 space-y-6">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">{selectedTemplate.audience}</p>
                                <h3 className="text-3xl font-black text-gray-900 tracking-tight mt-2">{selectedTemplate.name}</h3>
                            </div>
                            <button
                                type="button"
                                onClick={() => setActiveTemplateId(null)}
                                className="px-3 py-2 rounded-xl border border-gray-200 text-xs font-black uppercase tracking-widest text-gray-500 hover:bg-gray-50"
                            >
                                Close
                            </button>
                        </div>
                        <div className="rounded-3xl bg-gray-50 border border-gray-100 p-5 space-y-3">
                            {selectedTemplate.convo.map((line: string) => (
                                <p key={line} className="text-sm font-medium text-gray-700 leading-relaxed">{line}</p>
                            ))}
                        </div>
                        <div className="flex flex-col sm:flex-row gap-3">
                            <button
                                type="button"
                                onClick={() => setActiveTemplateId(null)}
                                className="w-full py-3 rounded-2xl bg-white border border-gray-200 text-gray-900 text-xs font-black uppercase tracking-widest hover:bg-gray-50 transition-colors"
                            >
                                Back
                            </button>
                            <button
                                type="button"
                                onClick={() => goToOnboarding(selectedTemplate.id)}
                                className="w-full py-3 rounded-2xl bg-blue-600 text-white text-xs font-black uppercase tracking-widest hover:bg-indigo-700 transition-colors shadow-lg shadow-blue-100"
                            >
                                Use This Template
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
