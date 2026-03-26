'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Server, Cpu, Database, Network, ChevronLeft, Globe, Lock, Code } from 'lucide-react';

export default function ArchitecturePage() {
    const router = useRouter();

    return (
        <div className="bg-white min-h-screen selection:bg-blue-100">
            {/* Nav */}
            <nav className="fixed top-0 left-0 right-0 z-[100] bg-white/70 backdrop-blur-2xl border-b border-gray-100">
                <div className="max-w-5xl mx-auto px-8 h-20 flex items-center justify-between">
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

            <main className="max-w-5xl mx-auto px-8 pt-48 pb-32">
                <header className="space-y-6 mb-24">
                    <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-50 text-blue-600 rounded-full text-[10px] font-black uppercase tracking-widest">
                        <Server className="w-3 h-3" /> System Architecture
                    </div>
                    <h1 className="text-6xl font-black text-gray-900 tracking-tight leading-[1] max-w-3xl">
                        Engineered for <br />
                        <span className="text-blue-600">Enterprise Scale.</span>
                    </h1>
                    <p className="text-xl text-gray-500 font-medium max-w-2xl leading-relaxed">
                        The Tangent Cloud AI orchestration platform is built on 
                        production-grade infrastructure with global availability, 
                        contextual recall nodes, and neural routing.
                    </p>
                </header>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* Layer 1 */}
                    <article className="p-10 rounded-[2.5rem] bg-gray-50 border border-gray-100 space-y-6">
                        <div className="p-4 bg-blue-600 text-white rounded-2xl w-fit shadow-lg shadow-blue-200">
                            <Cpu className="w-6 h-6" />
                        </div>
                        <div>
                            <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-3">Neural Ingest Pipeline</h3>
                            <p className="text-gray-500 text-sm leading-relaxed font-medium">
                                Our recursive ingestion engine processes unstructured data from URLs, PDFs, and internal databases. 
                                It utilizes chunking algorithms with metadata preservation to ensure high-fidelity context retrieval.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2 pt-2">
                            {['Recursive Crawler', 'Metadata Header Tags', 'PDF Extraction'].map(tag => (
                                <span key={tag} className="px-3 py-1 bg-white border border-gray-200 rounded-full text-[9px] font-black uppercase tracking-widest text-gray-400">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </article>

                    {/* Layer 2 */}
                    <article className="p-10 rounded-[2.5rem] bg-white border border-gray-100 shadow-xl shadow-gray-50 space-y-6">
                        <div className="p-4 bg-indigo-600 text-white rounded-2xl w-fit shadow-lg shadow-indigo-200">
                            <Database className="w-6 h-6" />
                        </div>
                        <div>
                            <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-3">Hybrid Vector Store</h3>
                            <p className="text-gray-500 text-sm leading-relaxed font-medium">
                                Knowledge is persisted in a distributed vector database with hybrid search capabilities (Semantic + Keyword). 
                                Optimized for sub-200ms recall latency across multi-tenant environments.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2 pt-2">
                            {['Qdrant Partitioning', 'PostgreSQL Sink', 'Redis Cache'].map(tag => (
                                <span key={tag} className="px-3 py-1 bg-gray-50 border border-transparent rounded-full text-[9px] font-black uppercase tracking-widest text-gray-500">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </article>

                    {/* Layer 3 */}
                    <article className="p-10 rounded-[2.5rem] bg-white border border-gray-100 shadow-xl shadow-gray-50 space-y-6">
                        <div className="p-4 bg-purple-600 text-white rounded-2xl w-fit shadow-lg shadow-purple-200">
                            <Globe className="w-6 h-6" />
                        </div>
                        <div>
                            <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-3">Enterprise Edge</h3>
                            <p className="text-gray-500 text-sm leading-relaxed font-medium">
                                Lightweight JS widgets are served via a global CDN with domain-restricted script policies. 
                                Context-aware greetings are triggered at the edge to minimize UI blocking.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2 pt-2">
                            {['Vercel Edge SDK', 'CSP Domain Limiting', 'Async hydration'].map(tag => (
                                <span key={tag} className="px-3 py-1 bg-gray-50 border border-transparent rounded-full text-[9px] font-black uppercase tracking-widest text-gray-500">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </article>

                    {/* Layer 4 */}
                    <article className="p-10 rounded-[2.5rem] bg-gray-50 border border-gray-100 space-y-6">
                        <div className="p-4 bg-teal-600 text-white rounded-2xl w-fit shadow-lg shadow-teal-200">
                            <Shield className="w-6 h-6" />
                        </div>
                        <div>
                            <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-3">Observability Stack</h3>
                            <p className="text-gray-500 text-sm leading-relaxed font-medium">
                                Real-time telemetry via OpenTelemetry and Prometheus. 
                                Every LLM call is traced for performance, hallucination rates, and cost management.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2 pt-2">
                            {['OTLP Tracing', 'Sentry Error Logs', 'Usage quotas'].map(tag => (
                                <span key={tag} className="px-3 py-1 bg-white border border-gray-200 rounded-full text-[9px] font-black uppercase tracking-widest text-gray-400">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </article>
                </div>

                <div className="mt-24 p-12 rounded-[3.5rem] bg-gray-900 text-white space-y-8 overflow-hidden relative group">
                    <div className="absolute top-0 right-0 p-12 opacity-10 group-hover:scale-110 transition-transform">
                        <Code className="w-32 h-32" />
                    </div>
                    <div className="space-y-4 relative z-10">
                        <h3 className="text-3xl font-black tracking-tight">Deployment Flexibility</h3>
                        <p className="text-gray-400 max-w-2xl font-medium leading-relaxed">
                            While our default SaaS offering runs on managed Tanegnt Cloud nodes, 
                            enterprise clients can opt for Private VPC deployments and custom 
                            LLM endpoint routing for maximum data sovereignty.
                        </p>
                    </div>
                </div>
            </main>

            <footer className="py-20 border-t border-gray-100 bg-gray-50/50">
                <div className="max-w-5xl mx-auto px-8 flex justify-between items-center gap-8">
                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest">© 2026 Tangent Cloud Technologies</p>
                    <div className="flex items-center gap-2 text-xs font-black text-gray-900">
                        <Lock className="w-4 h-4 text-blue-600" /> SOC2 Compliant Pathways
                    </div>
                </div>
            </footer>
        </div>
    );
}
