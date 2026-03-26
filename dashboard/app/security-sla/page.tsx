'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Shield, ChevronLeft, Lock, Zap, Clock, Bell, Settings } from 'lucide-react';

export default function SecuritySLAPage() {
    const router = useRouter();

    const sections = [
        {
            icon: <Clock className="w-6 h-6" />,
            title: "99.9% Uptime Guarantee",
            content: "We guarantee that our core ingestion and retrieval services will be available for customers with a monthly uptime of at least 99.9%. Scheduled maintenance will occur during off-peak hours and will be communicated at least 48 hours in advance."
        },
        {
            icon: <Zap className="w-6 h-6" />,
            title: "Performance Targets",
            content: "Our system architecture is designed to support high-throughput environments. We target sub-500ms response latency for knowledge base queries and under 5-second processing time for individual documents and web pages under standard load."
        },
        {
            icon: <Shield className="w-6 h-6" />,
            title: "End-to-End Encryption",
            content: "All data is encrypted in transit using TLS 1.3 and at rest using industry-standard AES-256 encryption. We utilize hardware security modules (HSMs) for key management and rotate credentials periodically."
        },
        {
            icon: <Bell className="w-6 h-6" />,
            title: "Incident Response",
            content: "In the event of a security incident or service disruption, our engineering team follows strict triage and mitigation protocols. We provide real-time status updates and target an initial response time of under 30 minutes for critical issues."
        }
    ];

    return (
        <div className="bg-white min-h-screen selection:bg-blue-100 font-sans">
            {/* Nav */}
            <nav className="fixed top-0 left-0 right-0 z-[100] bg-white/70 backdrop-blur-2xl border-b border-gray-100">
                <div className="max-w-4xl mx-auto px-8 h-20 flex items-center justify-between">
                    <button 
                        onClick={() => router.push('/')}
                        className="flex items-center gap-2 text-gray-400 hover:text-blue-600 transition-colors group"
                    >
                        <ChevronLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
                        <span className="text-xs font-black uppercase tracking-widest">Back to Product</span>
                    </button>
                    <div className="flex items-center gap-2">
                        <img src="/img/logo.png" alt="Logo" className="w-6 h-6 object-contain" />
                        <span className="text-lg font-black text-gray-900 tracking-tighter">Tangent Cloud</span>
                    </div>
                </div>
            </nav>

            <main className="max-w-4xl mx-auto px-8 pt-48 pb-32">
                <header className="space-y-6 mb-24">
                    <div className="inline-flex items-center gap-2 px-3 py-1 bg-amber-50 text-amber-600 rounded-full text-[10px] font-black uppercase tracking-widest">
                        <Shield className="w-3 h-3" /> Reliability & Security SLA
                    </div>
                    <h1 className="text-5xl md:text-6xl font-black text-gray-900 tracking-tight leading-[1]">
                        Reliability You Can <br />
                        <span className="text-amber-600">Count On.</span>
                    </h1>
                    <p className="text-lg text-gray-500 font-medium leading-relaxed max-w-2xl">
                        Our commitments to security, performance, and uptime are 
                        foundational pillars of the Tangent Cloud ecosystem. 
                        We build for resilience and production-grade stability.
                    </p>
                </header>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {sections.map((section) => (
                        <div key={section.title} className="p-8 rounded-[2.5rem] bg-white border border-gray-100 shadow-sm hover:shadow-xl hover:border-amber-100 transition-all space-y-6">
                            <div className="p-4 bg-amber-50 text-amber-600 rounded-2xl w-fit">
                                {section.icon}
                            </div>
                            <div>
                                <h3 className="text-xl font-black text-gray-900 tracking-tight mb-3">{section.title}</h3>
                                <p className="text-gray-500 text-sm leading-relaxed font-medium">
                                    {section.content}
                                </p>
                            </div>
                        </div>
                    ))}
                </div>

                <div className="mt-24 p-12 rounded-[2.5rem] bg-amber-600 text-white space-y-8 relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-12 opacity-10 group-hover:scale-110 transition-transform">
                        <Settings className="w-32 h-32" />
                    </div>
                    <div className="space-y-4 relative z-10">
                        <h3 className="text-3xl font-black tracking-tight">Custom SLAs & Support</h3>
                        <p className="text-amber-100 max-w-2xl font-medium leading-relaxed">
                            For enterprise customers with critical workloads, we offer custom 
                            service level agreements with guaranteed 15-minute response times, 
                            TAM support, and dedicated cloud-native infra deployments.
                        </p>
                    </div>
                </div>
            </main>

            <footer className="py-20 border-t border-gray-100 bg-gray-50/50">
                <div className="max-w-4xl mx-auto px-8 flex justify-between items-center gap-8">
                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest">© 2026 Tangent Cloud Technologies</p>
                    <div className="flex items-center gap-2 text-xs font-black text-gray-900">
                        <Lock className="w-4 h-4 text-amber-600" /> Enterprise Secured
                    </div>
                </div>
            </footer>
        </div>
    );
}
