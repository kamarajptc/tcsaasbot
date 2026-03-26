'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Shield, ChevronLeft, Lock, FileText, CheckCircle2 } from 'lucide-react';

export default function PrivacyPolicyPage() {
    const router = useRouter();

    const sections = [
        {
            title: "Data Sovereignty",
            content: "You retain full ownership of all documents, text, and chat logs ingested by your AI agents. Tangent Cloud serves as a data processor for the sole purpose of enabling vector search and retrieval for your specific tenants."
        },
        {
            title: "LLM Processing Policy",
            content: "Data passed to our LLM endpoints (OpenAI, Anthropic, Bedrock) is used exclusively for response generation and is NOT used to train foundation models. All third-party providers are governed by enterprise-grade privacy agreements."
        },
        {
            title: "Metadata Retention",
            content: "We store conversation metadata (timestamps, response latency, sentiment) for analytics purposes within your dashboard. Raw chat logs are stored for 30 days by default and can be configured for automatic purging or archival."
        },
        {
            title: "Vector Data Protection",
            content: "Vector embeddings representing your organizational knowledge are stored in logically isolated database partitions. Every vector search request is validated against your unique tenant key to prevent cross-tenant data leakage."
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
                    <div className="inline-flex items-center gap-2 px-3 py-1 bg-green-50 text-green-600 rounded-full text-[10px] font-black uppercase tracking-widest">
                        <Shield className="w-3 h-3" /> Privacy & Governance
                    </div>
                    <h1 className="text-5xl md:text-6xl font-black text-gray-900 tracking-tight leading-[1]">
                        Data Transparency <br />
                        <span className="text-green-600">Built-in.</span>
                    </h1>
                    <p className="text-lg text-gray-500 font-medium leading-relaxed max-w-2xl">
                        Last Updated: March 26, 2026. <br />
                        At Tangent Cloud, we prioritize your data security above all else. 
                        We believe that enterprise AI tools must be built on a foundation of 
                        zero-trust architecture and radical transparency.
                    </p>
                </header>

                <div className="space-y-16">
                    {sections.map((section) => (
                        <section key={section.title} className="space-y-6 pb-12 border-b border-gray-50 last:border-0">
                            <h3 className="text-2xl font-black text-gray-900 tracking-tight flex items-center gap-3">
                                <div className="w-1.5 h-6 bg-green-500 rounded-full" />
                                {section.title}
                            </h3>
                            <p className="text-gray-500 text-lg leading-relaxed font-medium">
                                {section.content}
                            </p>
                        </section>
                    ))}
                </div>

                <div className="mt-24 p-12 rounded-[2.5rem] bg-gray-50 border border-gray-100 grid grid-cols-1 md:grid-cols-2 gap-10 items-center">
                    <div className="space-y-6">
                        <h3 className="text-3xl font-black text-gray-900 tracking-tight">Compliance & Rights</h3>
                        <p className="text-gray-500 font-medium leading-relaxed mb-6">
                            We are committed to helping our customers meet their regulatory requirements across all jurisdictions.
                        </p>
                        <div className="space-y-3">
                            {['GDPR Data Protection', 'CCPA Right to Erasure', 'SOC2 Compliance Workstream'].map(item => (
                                <div key={item} className="flex items-center gap-3 text-xs font-black text-gray-800 uppercase tracking-widest">
                                    <CheckCircle2 className="w-4 h-4 text-green-600" /> {item}
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="p-8 bg-white rounded-3xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center gap-4">
                        <div className="w-20 h-20 bg-green-50 rounded-full flex items-center justify-center">
                            <FileText className="w-10 h-10 text-green-600" />
                        </div>
                        <p className="text-sm font-black text-gray-900 uppercase tracking-widest">Full Legal Document</p>
                        <p className="text-xs text-gray-400 font-medium">Standard DPA available for Enterprise clients upon request.</p>
                    </div>
                </div>
            </main>

            <footer className="py-20 border-t border-gray-100 bg-gray-50/50">
                <div className="max-w-4xl mx-auto px-8 flex justify-between items-center gap-8">
                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest">© 2026 Tangent Cloud Technologies</p>
                    <div className="flex items-center gap-2 text-xs font-black text-gray-900">
                        <Lock className="w-4 h-4 text-green-600" /> AES-256 Encrypted
                    </div>
                </div>
            </footer>
        </div>
    );
}
