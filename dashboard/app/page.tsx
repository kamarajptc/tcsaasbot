'use client';

import { BotList } from '@/components/BotList';
import { KnowledgeBase } from '@/components/KnowledgeBase';
import { Stats } from '@/components/Stats';
import { ConversationLog } from '@/components/ConversationLog';
import { Settings as SettingsComponent } from '@/components/Settings';
import { Leads as LeadsComponent } from '@/components/Leads';
import { Analytics as AnalyticsComponent } from '@/components/Analytics';
import { LandingPage } from '@/components/LandingPage';
import { KnowledgeAudit } from '@/components/KnowledgeAudit';
import { QualityCenter } from '@/components/QualityCenter';
import { CustomersRealtimeReport } from '@/components/CustomersRealtimeReport';
import { AdminPlansDashboard } from '@/components/AdminPlansDashboard';
import { ONBOARDING_BANNER_DISMISSED_KEY } from '@/lib/uiFlags';
import { dashboardApi, isValidToken } from '@/lib/api';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  Bot, Book, MessageSquare, Settings as SettingsIcon,
  LayoutDashboard, ExternalLink, Plus, Rocket,
  ShieldCheck, Bell, Users, BarChart3,
  X, LogOut, ChevronRight, Sparkles, Activity, BrainCircuit,
  Menu
} from 'lucide-react';
import { AIReport } from '@/components/AIReport';
import { useState, useEffect, useMemo, useRef, Suspense } from 'react';


function DashboardPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedView = searchParams.get('view');
  const requestedEditBotIdParam = searchParams.get('editBotId');
  const onboardedFlag = searchParams.get('onboarded') === '1';
  const validViews = ['dashboard', 'bots', 'knowledge', 'conversations', 'settings', 'leads', 'analytics', 'ai-reports', 'audit', 'quality', 'customers-realtime', 'client-plans', 'embed-test'] as const;
  type DashboardView = (typeof validViews)[number];

  const isValidView = (value: string): value is DashboardView => {
    return (validViews as readonly string[]).includes(value);
  };

  let initialView: DashboardView = 'dashboard';
  if (requestedView && isValidView(requestedView)) {
    initialView = requestedView;
  } else if (pathname.includes('reports/ai-agent')) {
    initialView = 'ai-reports';
  }
  const initialEditBotId = requestedEditBotIdParam && !Number.isNaN(Number(requestedEditBotIdParam))
    ? Number(requestedEditBotIdParam)
    : undefined;
  const startInDashboard = searchParams.get('start') === 'dashboard';

  const [view, setView] = useState<DashboardView>(initialView);
  const [isLanding, setIsLanding] = useState(() => {
    if (typeof window === 'undefined') return true;
    const token = localStorage.getItem('access_token');
    return !isValidToken(token);
  });
  const [onboardingBannerDismissed, setOnboardingBannerDismissed] = useState(() => {
    if (globalThis.window === undefined) return false;
    return globalThis.localStorage.getItem(ONBOARDING_BANNER_DISMISSED_KEY) === '1';
  });
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [initCreateNonce, setInitCreateNonce] = useState(0);
  const isAdmin = useMemo(() => {
    return userEmail?.toLowerCase().trim() === 'ops@tangentcloud.in';
  }, [userEmail]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notifications, setNotifications] = useState<Array<{
    id: string;
    title: string;
    body: string;
    createdAt: string;
    unread: boolean;
    actionView: DashboardView;
    conversationId?: number;
  }>>([]);
  const notificationPanelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (globalThis.window !== undefined) {
      const storedEmail = localStorage.getItem('tcsaas_api_key');
      const token = localStorage.getItem('access_token');
      
      setUserEmail(storedEmail);
      
      if (!isLanding && !isValidToken(token)) {
        setIsLanding(true);
        localStorage.removeItem('access_token');
        localStorage.removeItem('tcsaas_api_key');
      }
    }
  }, [isLanding]);

  const showOnboardingBanner = onboardedFlag && !onboardingBannerDismissed;
  const unreadNotifications = useMemo(() => notifications.filter((item) => item.unread).length, [notifications]);


  // Cleaning up URL params after consume
  useEffect(() => {
    if (!requestedEditBotIdParam && !onboardedFlag) return;
    
    // We only clean once manually to avoid frequent re-runs and flickering
    const timer = setTimeout(() => {
      const params = new URLSearchParams(searchParams.toString());
      let changed = false;
      if (requestedEditBotIdParam) {
        params.delete('editBotId');
        changed = true;
      }
      if (onboardedFlag) {
        params.delete('onboarded');
        changed = true;
      }
      
      if (changed) {
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname);
      }
    }, 1000);
    
    return () => clearTimeout(timer);
  }, [requestedEditBotIdParam, onboardedFlag, searchParams, router, pathname]);

  // Strict Security: Redirect non-admins away from admin views
  useEffect(() => {
    if (userEmail && !isAdmin && view === 'client-plans') {
      setView('dashboard');
    }
  }, [isAdmin, userEmail, view]);

  const dismissOnboardingBanner = () => {
    globalThis.localStorage.setItem(ONBOARDING_BANNER_DISMISSED_KEY, '1');
    setOnboardingBannerDismissed(true);
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('tcsaas_api_key');
    setIsLanding(true);
    router.push('/');
  };

  const handleInitAgent = () => {
    setView('bots');
    setInitCreateNonce((prev) => prev + 1);
  };

  const markAllNotificationsRead = () => {
    setNotifications((prev) => prev.map((item) => ({ ...item, unread: false })));
  };

  const openNotification = (notificationId: string) => {
    const selected = notifications.find((n) => n.id === notificationId);
    if (!selected) return;
    setNotifications((prev) => prev.map((n) => (
      n.id === notificationId ? { ...n, unread: false } : n
    )));
    setNotificationsOpen(false);
    setView(selected.actionView);
  };

  useEffect(() => {
    const fetchNotifications = async () => {
      setNotificationsLoading(true);
      try {
        const response = await dashboardApi.getConversations();
        const generated = (response.data || []).slice(0, 8).map((conv: any) => ({
          id: `conv-${conv.id}`,
          title: conv.bot_name || 'Anonymous User',
          body: conv.last_message || 'New conversation activity detected.',
          createdAt: conv.created_at,
          unread: true,
          actionView: 'conversations' as DashboardView,
          conversationId: conv.id,
        }));

        if (generated.length === 0) {
          setNotifications([{
            id: 'system-welcome',
            title: 'System Online',
            body: 'No active alerts. Your workspace is running normally.',
            createdAt: new Date().toISOString(),
            unread: false,
            actionView: 'dashboard',
          }]);
        } else {
          setNotifications(generated);
        }
      } catch {
        setNotifications([{
          id: 'system-fallback',
          title: 'Notification Feed',
          body: 'Live feed temporarily unavailable. Retry in a moment.',
          createdAt: new Date().toISOString(),
          unread: true,
          actionView: 'dashboard',
        }]);
      } finally {
        setNotificationsLoading(false);
      }
    };

    if (!isLanding) {
      fetchNotifications();
      const timer = globalThis.setInterval(fetchNotifications, 30000);
      return () => globalThis.clearInterval(timer);
    }
  }, [isLanding]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (!notificationPanelRef.current) return;
      if (!notificationPanelRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  if (isLanding) {
    return <LandingPage onGetStarted={() => setIsLanding(false)} />;
  }


  const getTitle = () => {
    switch (view) {
      case 'dashboard': return 'System Overview';
      case 'bots': return 'Neural Agents';
      case 'knowledge': return 'Core Intel';
      case 'conversations': return 'Signal Logs';
      case 'settings': return 'Global Config';
      case 'leads': return 'Pipeline CRM';
      case 'analytics': return 'Quantum Growth';
      case 'ai-reports': return 'Autonomous Intel';
      case 'audit': return 'Knowledge Audit';
      case 'quality': return 'Quality Command Center';
      case 'customers-realtime': return 'Customers Real-Time';
      case 'client-plans': return 'Enterprise Policy Terminal';
      case 'embed-test': return 'Embed Script Tester';
      default: return 'Nexus';
    }
  };

  const menuItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: 'Overview', group: 'Core' },
    { id: 'knowledge', icon: Book, label: 'Core Intelligence', group: 'Core' },
    { id: 'client-plans', icon: ShieldCheck, label: 'Client Plans', group: 'Admin' },
    { id: 'bots', icon: Bot, label: 'Agents', group: 'Management' },
    { id: 'conversations', icon: MessageSquare, label: 'Transactions', group: 'Management' },
    { id: 'analytics', icon: BarChart3, label: 'Analytics', group: 'Management' },
    { id: 'customers-realtime', icon: Activity, label: 'Customers RT', group: 'Management' },
    { id: 'ai-reports', icon: BrainCircuit, label: 'AI Reports', group: 'Management' },
    { id: 'audit', icon: ShieldCheck, label: 'Audit', group: 'Management' },
    { id: 'quality', icon: Activity, label: 'Quality', group: 'System' },
    { id: 'leads', icon: Users, label: 'Pipeline', group: 'Management' },
    { id: 'settings', icon: SettingsIcon, label: 'Parameters', group: 'System' },
    { id: 'embed-test', icon: Rocket, label: 'Embed Test', group: 'System' },
  ];

  const filteredMenuItems = menuItems.filter(item => {
    if (item.id === 'client-plans') return isAdmin;
    return true;
  });

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex font-sans selection:bg-blue-100 selection:text-blue-700">
      {/* Premium Sidebar */}
      <aside className="w-72 bg-white border-r border-gray-100 flex flex-col fixed h-full z-30 shadow-[4px_0_24px_rgba(0,0,0,0.02)]">
        <div className="p-8 h-24 flex items-center">
          <div className="flex items-center gap-3 group cursor-pointer">
            <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-lg shadow-gray-100 group-hover:scale-105 transition-transform duration-500 p-1">
              <img src="/img/logo.png" alt="Logo" className="w-full h-full object-contain" />
            </div>
            <span className="font-black text-2xl tracking-tighter text-gray-900 group-hover:tracking-normal transition-all duration-500">Tangent Cloud</span>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-8 overflow-y-auto no-scrollbar py-4">
          {(isAdmin ? ['Admin', 'Core', 'Management', 'System'] : ['Core', 'Management', 'System']).map((group) => {
            const items = filteredMenuItems.filter(item => item.group === group);
            if (items.length === 0) return null;
            return (
              <div key={group}>
                <p className="text-[10px] uppercase font-black text-gray-400 px-5 mb-4 tracking-[0.2em]">{group}</p>
                <div className="space-y-1">
                  {group === 'Admin' && isAdmin && items.filter(i => i.id === 'client-plans').map(item => (
                    <button
                      key={item.id}
                      onClick={() => setView('client-plans')}
                      className={`w-full flex items-center justify-between px-5 py-3.5 rounded-2xl font-bold transition-all duration-300 group ${view === 'client-plans'
                        ? 'bg-blue-600 text-white shadow-2xl shadow-blue-200 translate-x-1'
                        : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                        }`}
                    >
                      <div className="flex items-center gap-4">
                        <item.icon className={`w-5 h-5 ${view === 'client-plans' ? 'text-blue-400' : 'text-gray-400 group-hover:text-gray-900'} transition-colors`} />
                        <span className="text-sm">{item.label}</span>
                      </div>
                      {view === 'client-plans' && <ChevronRight className="w-4 h-4 text-gray-600" />}
                    </button>
                  ))}
                  {items.filter(i => i.id !== 'client-plans').map(item => (
                  <button
                    key={item.id}
                    onClick={() => setView(item.id as any)}
                    className={`w-full flex items-center justify-between px-5 py-3.5 rounded-2xl font-bold transition-all duration-300 group ${view === item.id
                      ? 'bg-blue-600 text-white shadow-2xl shadow-blue-200 translate-x-1'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                      }`}
                  >
                    <div className="flex items-center gap-4">
                      <item.icon className={`w-5 h-5 ${view === item.id ? 'text-blue-400' : 'text-gray-400 group-hover:text-gray-900'} transition-colors`} />
                      <span className="text-sm">{item.label}</span>
                    </div>
                    {view === item.id && <ChevronRight className="w-4 h-4 text-gray-600" />}
                  </button>
                ))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="p-6 mt-auto">
          <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-[2rem] p-6 text-white relative overflow-hidden group">
            <div className="relative z-10">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-white/10 backdrop-blur-md rounded-xl flex items-center justify-center border border-white/20">
                  <Activity className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/50">Pro Plan</p>
                  <p className="text-xs font-bold">Unlimited Agents</p>
                </div>
              </div>
              <button 
                onClick={() => setView('client-plans')}
                className="w-full py-2.5 bg-white text-gray-900 rounded-xl text-xs font-black shadow-xl hover:-translate-y-1 transition-all active:scale-95"
              >
                Upgrade Node
              </button>
            </div>
            <Sparkles className="absolute -right-4 -bottom-4 w-20 h-20 text-white/5 rotate-12 group-hover:rotate-45 transition-transform duration-1000" />
          </div>

          <div className="mt-8 flex items-center gap-4 px-2">
            <div className="w-10 h-10 bg-blue-100 rounded-2xl flex items-center justify-center text-blue-700 font-black shadow-inner uppercase">
              {userEmail ? userEmail[0] : 'A'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-black text-gray-900 truncate uppercase tracking-tighter">
                {userEmail ? userEmail.split('@')[0] : 'Admin Terminal'}
              </p>
              <p className="text-[10px] text-green-500 font-bold uppercase tracking-widest truncate">
                {userEmail || 'Master Access'}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-300 hover:text-red-500 transition-colors group relative"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
              <span className="absolute -top-8 right-0 bg-blue-600 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none font-bold uppercase tracking-widest whitespace-nowrap">
                Sign Out
              </span>
            </button>
          </div>

        </div>
      </aside>
      
      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 z-40 bg-gray-900/50 backdrop-blur-sm lg:hidden animate-in fade-in duration-300"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Drawer */}
      <aside className={`fixed inset-y-0 left-0 z-50 w-72 bg-white shadow-2xl transform transition-transform duration-300 lg:hidden flex flex-col ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-8 h-24 flex items-center justify-between">
           <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-lg p-1">
              <img src="/img/logo.png" alt="Logo" className="w-full h-full object-contain" />
            </div>
            <span className="font-black text-xl tracking-tighter text-gray-900">Tangent Cloud</span>
          </div>
          <button onClick={() => setMobileMenuOpen(false)} className="p-2 text-gray-400 hover:text-gray-900">
            <X className="w-6 h-6" />
          </button>
        </div>
        <nav className="flex-1 px-4 space-y-8 overflow-y-auto no-scrollbar py-4">
          {(isAdmin ? ['Admin', 'Core', 'Management', 'System'] : ['Core', 'Management', 'System']).map((group) => {
            const items = filteredMenuItems.filter(item => item.group === group);
            if (items.length === 0) return null;
            return (
              <div key={group}>
                <p className="text-[10px] uppercase font-black text-gray-400 px-5 mb-4 tracking-[0.2em]">{group}</p>
                <div className="space-y-1">
                  {group === 'Admin' && isAdmin && items.filter(i => i.id === 'client-plans').map(item => (
                    <button
                      key={item.id}
                      onClick={() => { setView('client-plans'); setMobileMenuOpen(false); }}
                      className={`w-full flex items-center justify-between px-5 py-3.5 rounded-2xl font-bold transition-all duration-300 ${view === 'client-plans' ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-gray-900'}`}
                    >
                      <div className="flex items-center gap-4">
                        <item.icon className={`w-5 h-5 ${view === 'client-plans' ? 'text-blue-400' : 'text-gray-400'}`} />
                        <span className="text-sm">{item.label}</span>
                      </div>
                    </button>
                  ))}
                  {items.filter(i => i.id !== 'client-plans').map(item => (
                    <button
                      key={item.id}
                      onClick={() => { setView(item.id as any); setMobileMenuOpen(false); }}
                      className={`w-full flex items-center justify-between px-5 py-3.5 rounded-2xl font-bold transition-all duration-300 ${view === item.id ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-gray-900'}`}
                    >
                      <div className="flex items-center gap-4">
                        <item.icon className={`w-5 h-5 ${view === item.id ? 'text-blue-400' : 'text-gray-400'}`} />
                        <span className="text-sm">{item.label}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 lg:ml-72 flex flex-col min-h-screen">
        <header className="h-24 bg-white/70 backdrop-blur-2xl border-b border-gray-100 flex items-center justify-between px-6 lg:px-10 sticky top-0 z-20">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 text-gray-400 hover:text-gray-900 hover:bg-gray-50 rounded-xl"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="flex flex-col">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-black text-gray-900 tracking-tight">{getTitle()}</h1>
                <div className="px-2.5 py-1 bg-green-50 rounded-lg text-[9px] font-black text-green-600 border border-green-100 uppercase tracking-widest">Local-9100</div>
                {isAdmin && <div className="px-2.5 py-1 bg-blue-50 rounded-lg text-[9px] font-black text-blue-600 border border-blue-100 uppercase tracking-widest flex items-center gap-1.5 shadow-sm shadow-blue-100 animate-in fade-in slide-in-from-left-2 transition-all"><ShieldCheck className="w-3 h-3 text-blue-500" /> Root Admin</div>}
              </div>
              <p className="text-[10px] font-black text-gray-700 uppercase tracking-widest mt-1">Operational Environment: {isAdmin ? `Unified Policy Control [Admin: ${userEmail}]` : `Production Ready [User: ${userEmail}]`}</p>
            </div>
          </div>

          <div className="flex items-center gap-8">
            <div className="hidden xl:flex items-center gap-6 border-r border-gray-100 pr-8">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_#22c55e]" />
                <span className="text-[10px] font-black text-gray-700 uppercase tracking-widest">API Status: Optimal</span>
              </div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-500" />
                <span className="text-[10px] font-black text-gray-700 uppercase tracking-widest">Identity: Verified</span>
              </div>
            </div>

            <div className="relative flex items-center gap-4" ref={notificationPanelRef}>
              <button
                onClick={() => setNotificationsOpen((open) => !open)}
                className="relative w-12 h-12 bg-gray-50 rounded-2xl flex items-center justify-center text-gray-400 hover:text-gray-900 hover:bg-gray-100 transition-all group micro-press"
                type="button"
                aria-label="Open notifications"
              >
                <Bell className="w-5 h-5" />
                {unreadNotifications > 0 && (
                  <span className="absolute top-2 right-2 min-w-4 h-4 px-1 bg-red-500 text-white rounded-full border-2 border-white text-[9px] font-black flex items-center justify-center group-hover:scale-110 transition-transform">
                    {unreadNotifications > 9 ? '9+' : unreadNotifications}
                  </span>
                )}
              </button>
              {notificationsOpen && (
                <div className="absolute right-44 top-20 w-[28rem] max-h-[28rem] overflow-hidden rounded-[1.75rem] border border-gray-100 bg-white shadow-2xl shadow-blue-200/60 animate-in slide-in-from-top-2 fade-in duration-200 z-40">
                  <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-black text-gray-900">Notification Stream</p>
                      <p className="text-[10px] uppercase tracking-widest font-black text-gray-400">
                        {unreadNotifications} unread signals
                      </p>
                    </div>
                    <button
                      onClick={markAllNotificationsRead}
                      className="text-[10px] uppercase tracking-widest font-black text-blue-600 hover:text-blue-700"
                      type="button"
                    >
                      Mark all read
                    </button>
                  </div>
                  <div className="max-h-[22rem] overflow-y-auto">
                    {notificationsLoading ? (
                      <div className="p-8 text-center text-[11px] font-bold text-gray-500">Loading notifications...</div>
                    ) : (
                      notifications.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => openNotification(item.id)}
                          className="w-full text-left px-6 py-4 border-b border-gray-50 hover:bg-gray-50/80 transition-colors group"
                          type="button"
                        >
                          <div className="flex items-start gap-3">
                            <div className={`mt-1 w-2.5 h-2.5 rounded-full ${item.unread ? 'bg-blue-500 animate-pulse' : 'bg-gray-200'}`} />
                            <div className="min-w-0">
                              <p className="text-sm font-black text-gray-900 truncate">{item.title}</p>
                              <p className="text-xs text-gray-500 mt-1 line-clamp-2">{item.body}</p>
                              <p className="text-[10px] uppercase tracking-widest font-black text-gray-300 mt-2">
                                {new Date(item.createdAt).toLocaleString()}
                              </p>
                            </div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
              <button
                onClick={handleInitAgent}
                className="flex items-center gap-3 px-6 py-3 bg-blue-600 text-white rounded-[1.25rem] text-xs font-black hover:bg-indigo-600 hover:-translate-y-1 transition-all active:scale-95 shadow-2xl shadow-blue-100 micro-press"
                type="button"
              >
                <Plus className="w-4 h-4" />
                INIT AGENT
              </button>
            </div>
          </div>
        </header>

        <div className="p-10 max-w-7xl mx-auto w-full space-y-10">
          {showOnboardingBanner && (
            <div className="rounded-[2.5rem] border border-green-100 bg-green-50/50 backdrop-blur-xl px-8 py-6 flex items-center justify-between gap-6 shadow-xl shadow-green-100/20 animate-in slide-in-from-top-4 duration-500">
              <div className="flex items-center gap-6">
                <div className="w-12 h-12 bg-green-100 rounded-2xl flex items-center justify-center text-green-600 border border-green-200 shadow-inner">
                  <Rocket className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-sm font-black text-green-900 uppercase tracking-tight">Deployment Successful</h4>
                  <p className="text-xs font-medium text-green-700/80 mt-1">Your core infrastructure is now online. Initialize agents to begin signal processing.</p>
                </div>
              </div>
              <button onClick={dismissOnboardingBanner} className="p-3 rounded-2xl text-green-800 hover:bg-green-100 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
          )}

          {view === 'dashboard' && (
            <div className="space-y-12 animate-in fade-in duration-700 micro-view-shell">
              {/* Hero Banner */}
              <div className="relative overflow-hidden bg-white ring-1 ring-gray-100 rounded-[3rem] p-12 shadow-2xl shadow-blue-200/50 group">
                <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-12">
                  <div className="max-w-xl space-y-6">
                    <h2 className="text-4xl font-black text-gray-900 tracking-tighter leading-tight">
                      Neural Interface <span className="text-blue-600">Active</span>.
                    </h2>
                    <p className="text-gray-500 text-base leading-relaxed font-medium">
                      Your autonomous fleet processed <span className="text-gray-900 font-black">2,482 blocks</span> of intelligence today.
                      Global latency is holding steady at <span className="text-blue-600 font-black tracking-tight">142ms</span>.
                    </p>
                    <div className="flex gap-4 pt-4">
                      <button onClick={() => setView('bots')} className="px-8 py-4 bg-blue-600 text-white rounded-[1.5rem] font-black text-xs uppercase tracking-widest shadow-2xl shadow-blue-200 hover:bg-indigo-600 hover:-translate-y-1 transition-all active:scale-95">Command Center</button>
                      <button onClick={() => setView('knowledge')} className="px-8 py-4 bg-white text-gray-900 border border-gray-100 rounded-[1.5rem] font-black text-xs uppercase tracking-widest hover:bg-gray-50 transition-all flex items-center gap-2">
                        Update Intel <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 flex justify-center">
                    <div className="w-64 h-64 bg-gray-50 rounded-[3rem] flex items-center justify-center relative shadow-inner overflow-hidden">
                      <Rocket className="w-32 h-32 text-gray-200 transform group-hover:-translate-y-4 transition-transform duration-700" />
                      <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>
                </div>

                {/* Background Shapes */}
                <div className="absolute -right-20 -top-20 w-80 h-80 bg-blue-50 rounded-full blur-[100px] opacity-60" />
                <div className="absolute right-20 bottom-0 p-8 opacity-5 text-gray-900">
                  <Activity className="w-64 h-64" />
                </div>
              </div>

              <Stats />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div className="bg-white rounded-[3rem] border border-gray-100 p-10 shadow-xl shadow-blue-200/30">
                  <div className="flex justify-between items-center mb-10">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center text-blue-600 shadow-inner border border-blue-100">
                        <Activity className="w-5 h-5" />
                      </div>
                      <h3 className="text-xl font-black text-gray-900 tracking-tight">Signal Feed</h3>
                    </div>
                    <button onClick={() => setView('conversations')} className="text-[10px] font-black text-blue-600 uppercase tracking-widest flex items-center gap-1 hover:underline">
                      Real-time Audit <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>
                  <div className="space-y-6">
                    {[1, 2, 3].map(i => (
                      <div key={i} className="flex items-center gap-6 p-6 hover:bg-gray-50 rounded-3xl transition-all border border-transparent hover:border-gray-100 group">
                        <div className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-gray-400 group-hover:bg-blue-600 group-hover:text-white group-hover:rotate-12 transition-all duration-500 shadow-sm border border-gray-50">
                          <MessageSquare className="w-6 h-6" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm font-black text-gray-900">Transmission Synchronized</p>
                          <p className="text-[10px] text-gray-400 font-bold uppercase tracking-widest mt-1">2m ago • Node: San Francisco</p>
                        </div>
                        <div className="text-[10px] font-black text-green-600 bg-green-50 px-3 py-1 rounded-lg border border-green-100">STABLE</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white rounded-[3rem] border border-gray-100 p-10 shadow-xl shadow-blue-200/30">
                  <div className="flex justify-between items-center mb-10">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center text-indigo-600 shadow-inner border border-indigo-100">
                        <Book className="w-5 h-5" />
                      </div>
                      <h3 className="text-xl font-black text-gray-900 tracking-tight">Intel Repository</h3>
                    </div>
                    <button onClick={() => setView('knowledge')} className="text-[10px] font-black text-indigo-600 uppercase tracking-widest flex items-center gap-1 hover:underline">
                      Database Access <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="p-10 bg-gray-50/50 rounded-[2.5rem] border-2 border-dashed border-gray-100 flex flex-col items-center justify-center text-center space-y-6">
                    <div className="w-20 h-20 bg-white rounded-[2rem] shadow-xl flex items-center justify-center text-gray-200 relative">
                      <Book className="w-10 h-10" />
                      <div className="absolute -top-2 -right-2 w-6 h-6 bg-indigo-600 rounded-full border-4 border-white flex items-center justify-center">
                        <div className="w-1 h-1 bg-white rounded-full animate-ping" />
                      </div>
                    </div>
                    <div>
                      <p className="text-sm font-black text-gray-900 uppercase">12 Nodes Ingested</p>
                      <p className="text-[10px] text-gray-400 font-bold uppercase tracking-widest mt-1">Last crawl integrity: High</p>
                    </div>
                    <button onClick={() => setView('knowledge')} className="px-8 py-3 bg-white border border-gray-100 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl hover:-translate-y-1 transition-all">Re-Index Global Intel</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {view === 'bots' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <BotList
                key={`bots-${initCreateNonce}-${initialEditBotId ?? 'none'}`}
                initialEditBotId={initialEditBotId}
                initialCreate={initCreateNonce > 0}
              />
            </div>
          )}

          {view === 'knowledge' && (
            <div className="space-y-6 animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <KnowledgeBase />
            </div>
          )}

          {view === 'conversations' && (
            <div className="space-y-6 animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <ConversationLog />
            </div>
          )}

          {view === 'settings' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <SettingsComponent />
            </div>
          )}

          {view === 'leads' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <LeadsComponent />
            </div>
          )}

          {view === 'analytics' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <AnalyticsComponent />
            </div>
          )}
          {view === 'ai-reports' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <AIReport />
            </div>
          )}
          {view === 'audit' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <KnowledgeAudit />
            </div>
          )}
          {view === 'quality' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <QualityCenter />
            </div>
          )}
          {view === 'customers-realtime' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              <CustomersRealtimeReport />
            </div>
          )}
          {view === 'client-plans' && (
            <div className="animate-in slide-in-from-bottom-6 duration-700 micro-view-shell">
              {isAdmin ? <AdminPlansDashboard /> : <Stats />}
            </div>
          )}
          {view === 'embed-test' && (
            <div className="h-[calc(100vh-160px)] w-full rounded-[2.5rem] overflow-hidden border border-gray-100 shadow-2xl bg-white animate-in slide-in-from-bottom-6 duration-700">
              <iframe 
                src="/test_embed_manual.html" 
                className="w-full h-full border-none"
                title="Embed Tester"
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#F8FAFC]" />}>
      <DashboardPageContent />
    </Suspense>
  );
}
