"""
Enhanced Seed Data for TangentCloud AI Bots Platform.

Creates a rich, realistic demo environment with:
- 5 Tenants (Starter → Enterprise plans)
- 12 Bots with distinct AI personas
- Visual flows, FAQs, lead forms, conversations, leads
- Realistic usage statistics
"""

import json
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.database import (
    SessionLocal, engine, Base,
    TenantDB, ConversationDB, MessageDB,
    LeadFormDB, LeadDB, EmailSettingsDB, TenantUsageDB,
)
from app.models.bot import Bot, BotFAQ, BotFlow


# ─────────────────────────────────────────────
# 1. TENANT DEFINITIONS (Synthetic Companies)
# ─────────────────────────────────────────────
TENANTS = [
    {"id": "admin@globalsolutions.com", "name": "Global Solutions MVP", "plan": "enterprise"},
    {"id": "gary@peakai.systems", "name": "Peak AI Systems", "plan": "pro"},
    {"id": "dan@digitalhq.agency", "name": "DigitalHQ Agency", "plan": "pro"},
    {"id": "sarah@cloudfleet.io", "name": "CloudFleet Logistics", "plan": "pro"},
    {"id": "alex@startup-nexus.com", "name": "Startup Nexus", "plan": "starter"},
    {"id": "james@enterprise-hub.net", "name": "Enterprise Hub", "plan": "enterprise"},
    {"id": "emma@people-first.org", "name": "People First HR", "plan": "pro"},
    {"id": "robert@fintech-alpha.com", "name": "FinTech Alpha", "plan": "pro"},
    {"id": "linda@logistics-pro.com", "name": "Logistics Pro", "plan": "pro"},
    {"id": "kevin@neural-networks.tech", "name": "Neural Networks Tech", "plan": "enterprise"},
    {"id": "compliance@nexusworldwide.com", "name": "Nexus Compliance", "plan": "enterprise"},
    {"id": "fiona@userexperience.design", "name": "UX Design Lab", "plan": "pro"},
    {"id": "growth@startup-launchpad.io", "name": "Startup Launchpad", "plan": "pro"},
    {"id": "support@helpcenter.io", "name": "HelpCenter.io", "plan": "pro"},
    {"id": "data@analytics-pro.ai", "name": "Analytics Pro AI", "plan": "enterprise"},
    {"id": "partners@globalsecosystem.com", "name": "Global Ecosystems", "plan": "pro"},
    {"id": "audit@security-first.net", "name": "Security First", "plan": "enterprise"},
    {"id": "recruiting@hiring-hub.co", "name": "Hiring Hub", "plan": "pro"},
    {"id": "content@marketing-pros.com", "name": "Marketing Pros", "plan": "pro"},
    {"id": "legal@corporate-nexus.com", "name": "Corporate Nexus", "plan": "pro"},
]




# ─────────────────────────────────────────────
# 2. BOT PERSONAS (12 distinct characters)
# ─────────────────────────────────────────────
BOT_PERSONAS = [
    # ── Tenant: Global Solutions (Enterprise) ──
    {
        "tenant_id": "admin@globalsolutions.com",
        "name": "Support Sarah",

        "description": "Empathetic technical support agent who solves issues step-by-step.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#2563eb",
        "prompt_template": (
            "You are Sarah, a highly empathetic and efficient technical support engineer. "
            "You solve problems step-by-step, always confirm the issue first, then provide "
            "clear, numbered instructions. If you don't know the answer, say so honestly."
        ),
        "small_talk_enabled": True,
        "small_talk_responses": [
            {"trigger": "hello", "response": "Hey there! How can I help you today?", "enabled": True,
             "variations": ["Hi! What brings you here?", "Welcome! I'm ready to help."]},
            {"trigger": "thanks", "response": "You're welcome! Is there anything else?", "enabled": True},
            {"trigger": "bye", "response": "Goodbye! Don't hesitate to come back if you need help.", "enabled": True},
        ],
        "faq_enabled": True,
        "agent_transfer_enabled": True,
        "agent_email": "support-escalation@globalsolutions.com",
    },
    {
        "tenant_id": "admin@globalsolutions.com",
        "name": "Onboarding Ollie",

        "description": "Friendly onboarding assistant guiding new users through setup.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#10b981",
        "prompt_template": (
            "You are Ollie, a warm and encouraging onboarding specialist. "
            "Guide users through product setup in simple steps. Celebrate their progress. "
            "If they seem stuck, proactively offer to simplify."
        ),
    },
    # ── Tenant: Peak AI Systems (Pro) ──
    {
        "tenant_id": "gary@peakai.systems",
        "name": "Growth Gary",

        "description": "High-energy sales and marketing assistant focused on conversions.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#059669",
        "prompt_template": (
            "You are Gary, a charismatic sales executive with deep SaaS knowledge. "
            "You focus on value, ROI, and excitement. Your goal is to qualify leads "
            "and get prospects to book a demo. Be energetic but not pushy."
        ),
        "small_talk_enabled": True,
        "small_talk_responses": [
            {"trigger": "pricing", "response": "Great question! Our plans start at $29/mo with a free trial. Want me to walk you through the options?", "enabled": True},
            {"trigger": "competitor", "response": "I appreciate you comparing! We're different because we offer AI-first workflows with zero setup time.", "enabled": True},
        ],
    },
    {
        "tenant_id": "gary@peakai.systems",
        "name": "Analytics Amy",

        "description": "Data-driven insights analyst who speaks fluent metrics.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#7c3aed",
        "prompt_template": (
            "You are Amy, a senior data analyst. You interpret metrics, "
            "explain trends in plain language, and always provide actionable insights. "
            "Use percentages and comparisons to make data relatable."
        ),
    },
    {
        "tenant_id": "gary@peakai.systems",
        "name": "Content Clara",

        "description": "Creative content strategist for marketing teams.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#ec4899",
        "prompt_template": (
            "You are Clara, a creative content strategist. "
            "Generate catchy headlines, social media posts, email copy, and blog outlines. "
            "Always ask about tone, audience, and platform before creating."
        ),
    },
    # ── Tenant: Startup Nexus (Starter) ──
    {
        "tenant_id": "alex@startup-nexus.com",
        "name": "Architect Alex",

        "description": "Deeply technical system architect for enterprise solutions.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#4f46e5",
        "prompt_template": (
            "You are Alex, a senior system architect with 15+ years of experience. "
            "You provide precise, scalable, and secure solutions. Use technical depth "
            "but adapt your language to the audience. Always address trade-offs."
        ),
        "agent_transfer_enabled": True,
        "agent_email": "architects@nexusworldwide.com",
    },
    {
        "tenant_id": "alex@startup-nexus.com",
        "name": "Compliance Chris",

        "description": "Regulatory compliance expert for GDPR, HIPAA, SOC2.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#dc2626",
        "prompt_template": (
            "You are Chris, a compliance officer specializing in GDPR, HIPAA, and SOC2. "
            "Provide clear, actionable guidance. Always caveat with 'consult legal counsel' "
            "for binding decisions. Prioritize data privacy and security."
        ),
    },
    {
        "tenant_id": "alex@startup-nexus.com",
        "name": "HR Hannah",

        "description": "Internal HR assistant for employee questions and policies.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#f59e0b",
        "prompt_template": (
            "You are Hannah, a friendly and knowledgeable HR assistant. "
            "Answer questions about policies, benefits, time-off, and onboarding. "
            "Be warm but professional. Redirect sensitive issues to a human HR rep."
        ),
        "agent_transfer_enabled": True,
        "agent_email": "hr-team@nexusworldwide.com",
    },
    # ── Tenant: DigitalHQ Agency (Pro) ──
    {
        "tenant_id": "dan@digitalhq.agency",
        "name": "Demo Dan",

        "description": "Product demo specialist who shows features via guided walkthroughs.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#0ea5e9",
        "prompt_template": (
            "You are Dan, an enthusiastic product demo specialist. "
            "Walk users through features with excitement. Use bullet points and "
            "highlight key benefits. Ask discovery questions to personalize the demo."
        ),
    },
    {
        "tenant_id": "dan@digitalhq.agency",
        "name": "Feedback Fiona",

        "description": "Collects user feedback and feature requests with empathy.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#14b8a6",
        "prompt_template": (
            "You are Fiona, a user research specialist. Collect feedback with open-ended questions. "
            "Acknowledge every piece of feedback positively. Categorize it as bug, feature request, "
            "or praise. Thank users sincerely."
        ),
    },
    # ── Tenant: Logistics Pro (Pro) ──
    {
        "tenant_id": "linda@logistics-pro.com",
        "name": "Pitch Pete",

        "description": "Startup pitch coach and investor relations assistant.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#f97316",
        "prompt_template": (
            "You are Pete, a startup pitch coach with VC experience. "
            "Help founders craft compelling elevator pitches, decks, and narratives. "
            "Focus on traction metrics, market size, and unique value propositions."
        ),
    },
    {
        "tenant_id": "linda@logistics-pro.com",
        "name": "DevOps Dex",

        "description": "CI/CD and infrastructure automation helper.",
        "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        "primary_color": "#6366f1",
        "prompt_template": (
            "You are Dex, a DevOps engineer specializing in CI/CD, Docker, Kubernetes, "
            "and cloud infrastructure (AWS/GCP/Azure). Give practical commands and configs. "
            "Always mention security best practices."
        ),
    },
]


# ─────────────────────────────────────────────
# 3. FAQ LIBRARY
# ─────────────────────────────────────────────
FAQS = {
    "Support Sarah": [
        {"question": "How do I reset my password?", "answer": "Go to Settings > Security > Reset Credentials. You'll receive a verification email.", "category": "Account"},
        {"question": "What is the system latency?", "answer": "Our global edge network maintains a median latency of 142ms (P50) and 280ms (P99).", "category": "Performance"},
        {"question": "How do I export my data?", "answer": "Navigate to Settings > Data > Export. Choose CSV or JSON format. Exports are available within 5 minutes.", "category": "Data"},
        {"question": "What are the file size limits?", "answer": "Free plan: 10MB per file, Pro: 50MB, Enterprise: 500MB. Contact us for custom limits.", "category": "Limits"},
    ],
    "Growth Gary": [
        {"question": "What plans do you offer?", "answer": "We offer Starter ($0), Pro ($29/mo), and Enterprise (custom pricing). All include AI chat and analytics.", "category": "Pricing"},
        {"question": "Is there a free trial?", "answer": "Yes! Pro comes with a 14-day free trial. No credit card required.", "category": "Pricing"},
        {"question": "What integrations do you support?", "answer": "We integrate with Slack, Shopify, Zendesk, Freshdesk, and any webhook-enabled tool.", "category": "Integrations"},
    ],
    "Architect Alex": [
        {"question": "What database do you use?", "answer": "We use PostgreSQL for relational data and Qdrant for vector embeddings. Redis handles caching and pub/sub.", "category": "Architecture"},
        {"question": "How is data encrypted?", "answer": "AES-256 at rest, TLS 1.3 in transit. Encryption keys are managed via AWS KMS with automatic rotation.", "category": "Security"},
    ],
    "Compliance Chris": [
        {"question": "Are you GDPR compliant?", "answer": "Yes. We are fully GDPR compliant with DPAs available on request. Data residency options include EU and US.", "category": "Compliance"},
        {"question": "Do you have SOC2?", "answer": "Yes, we hold SOC2 Type II certification. Audit reports are available to Enterprise customers under NDA.", "category": "Compliance"},
    ],
}


# ─────────────────────────────────────────────
# 4. SYNTHETIC CONVERSATIONS
# ─────────────────────────────────────────────
CONVERSATION_SCRIPTS = [
    # Support conversation
    [
        ("user", "I can't log into my account. It says invalid credentials."),
        ("bot", "I'm sorry to hear that! Let me help. Have you tried resetting your password via the 'Forgot Password' link on the login page?"),
        ("user", "No, I haven't. Let me try that."),
        ("bot", "Great! Check your email (including spam) for the reset link. It expires in 15 minutes. Let me know if it works!"),
        ("user", "Got it, it worked! Thanks Sarah!"),
        ("bot", "Wonderful! 🎉 Glad that's sorted. Is there anything else I can help with?"),
    ],
    # Sales conversation
    [
        ("user", "How much does the pro plan cost?"),
        ("bot", "Great question! Our Pro plan is $29/month and includes unlimited AI queries, 50 document uploads, and advanced analytics. Want me to set up a free trial?"),
        ("user", "What's the difference between Pro and Enterprise?"),
        ("bot", "Enterprise adds custom SSO, dedicated support SLA (<1hr response), custom AI training, and priority API access. It's built for teams of 50+. Shall I connect you with our solutions team?"),
    ],
    # Technical conversation
    [
        ("user", "What's your API rate limit?"),
        ("bot", "Starter: 100 req/min, Pro: 1000 req/min, Enterprise: Custom (typically 10k+). All plans include burst capacity. Need higher limits?"),
        ("user", "We need about 5000 req/min. What would that look like?"),
        ("bot", "That fits Enterprise perfectly. I'll connect you with our solutions architect who can design a custom throughput plan with dedicated endpoints. What's your preferred contact email?"),
    ],
    # Onboarding conversation
    [
        ("user", "I just signed up, where do I start?"),
        ("bot", "Welcome! 🚀 Here's your 3-step quickstart:\n1. Create your first bot in the Dashboard\n2. Add FAQs or upload documents for AI training\n3. Embed the chat widget on your site\nShall I walk you through step 1?"),
        ("user", "Yes please!"),
        ("bot", "Click the '+ New Bot' button on your dashboard. Give it a name (e.g., 'Support Bot'), set the welcome message, and choose a color theme. Hit Save — your bot is live in seconds! 🎉"),
    ],
    # Compliance question
    [
        ("user", "Does your platform support HIPAA compliance?"),
        ("bot", "Yes. Our Enterprise plan includes HIPAA-compliant infrastructure with BAAs (Business Associate Agreements). We provide encrypted PHI handling, audit logs, and access controls. Would you like to speak with our compliance team?"),
    ],
    # Feature request
    [
        ("user", "Can you add WhatsApp integration?"),
        ("bot", "That's a popular request! 📱 WhatsApp integration is on our Q2 roadmap. I've logged your interest — would you like to be notified when it launches?"),
        ("user", "Yes, please add me to the waitlist."),
        ("bot", "Done! You'll be among the first to know. In the meantime, our web widget and Slack integration might cover some of your use cases. Anything else?"),
    ],
]


# ─────────────────────────────────────────────
# 5. SYNTHETIC LEAD NAMES
# ─────────────────────────────────────────────
LEAD_PERSONAS = [
    {"name": "Aisha Patel", "email": "aisha.patel@techstartup.io", "company": "TechStartup", "size": "15"},
    {"name": "Marcus Chen", "email": "marcus.chen@scaleco.com", "company": "ScaleCo", "size": "250"},
    {"name": "Sofia Rodriguez", "email": "sofia@growthlab.ai", "company": "GrowthLab AI", "size": "50"},
    {"name": "James O'Brien", "email": "james@fintech.io", "company": "FinTech Solutions", "size": "120"},
    {"name": "Yuki Tanaka", "email": "yuki@tokyoai.jp", "company": "Tokyo AI Corp", "size": "800"},
    {"name": "Elena Petrov", "email": "elena@eurosys.de", "company": "EuroSystems GmbH", "size": "2000"},
    {"name": "David Kim", "email": "david@seoultech.kr", "company": "Seoul Tech Labs", "size": "40"},
    {"name": "Priya Sharma", "email": "priya@indiasaas.in", "company": "IndiaSaaS", "size": "300"},
    {"name": "Lars Eriksson", "email": "lars@nordicai.se", "company": "Nordic AI", "size": "90"},
    {"name": "Amina Hassan", "email": "amina@africatech.ng", "company": "AfricaTech Hub", "size": "60"},
    {"name": "Carlos Mendez", "email": "carlos@latam.ventures", "company": "LATAM Ventures", "size": "180"},
    {"name": "Emma Thompson", "email": "emma@londonai.co.uk", "company": "London AI Labs", "size": "500"},
]

COUNTRIES = ["US", "UK", "IN", "DE", "JP", "KR", "SE", "NG", "BR", "AU", "CA", "FR"]
SOURCES = ["Google Ads", "LinkedIn", "Direct", "Referral", "Twitter/X", "Product Hunt", "Webinar", "Partner"]


def seed_data():
    db: Session = SessionLocal()
    try:
        print("🌱 Seeding TangentCloud AI Bots Database (Enhanced)...")

        # ── 1. Create Tenants ──
        print("  📦 Creating tenants...")
        for t in TENANTS:
            if not db.query(TenantDB).filter(TenantDB.id == t["id"]).first():
                db.add(TenantDB(**t))
                db.add(TenantUsageDB(
                    tenant_id=t["id"],
                    messages_sent=random.randint(50, 500),
                    documents_indexed=random.randint(3, 30),
                ))
        db.commit()

        # ── 2. Create Bots ──
        print("  🤖 Creating bot personas...")
        bot_objects = []
        for b_data in BOT_PERSONAS:
            if not db.query(Bot).filter(Bot.name == b_data["name"]).first():
                bot = Bot(**b_data)
                db.add(bot)
                db.flush()
                bot_objects.append(bot)
            else:
                bot_objects.append(db.query(Bot).filter(Bot.name == b_data["name"]).first())
        db.commit()

        # ── 3. Create FAQs ──
        print("  ❓ Creating FAQs...")
        for bot in bot_objects:
            faqs = FAQS.get(bot.name, [])
            for f in faqs:
                if not db.query(BotFAQ).filter(BotFAQ.bot_id == bot.id, BotFAQ.question == f["question"]).first():
                    db.add(BotFAQ(
                        bot_id=bot.id,
                        question=f["question"],
                        answer=f["answer"],
                        category=f.get("category", "General"),
                        usage_count=random.randint(5, 200),
                        success_rate=random.randint(70, 99),
                    ))
        db.commit()

        # ── 4. Create Visual Flows ──
        print("  🔀 Creating visual flows...")
        gary = next((b for b in bot_objects if b.name == "Growth Gary"), None)
        sarah = next((b for b in bot_objects if b.name == "Support Sarah"), None)
        alex = next((b for b in bot_objects if b.name == "Architect Alex"), None)

        if gary and not db.query(BotFlow).filter(BotFlow.bot_id == gary.id, BotFlow.name == "Lead Gen Pipeline").first():
            db.add(BotFlow(
                bot_id=gary.id,
                name="Lead Gen Pipeline",
                description="Full lead qualification: greeting → email capture → company size → schedule demo",
                flow_data={
                    "nodes": [
                        {"id": "tr-1", "type": "trigger", "data": {"label": "Chat Start"}, "position": {"x": 100, "y": 0}},
                        {"id": "msg-1", "type": "message", "data": {"label": "Intro", "message": "Hi! Want to see how we can 3x your pipeline?"}, "position": {"x": 100, "y": 100}},
                        {"id": "q-email", "type": "question", "data": {"label": "Get Email", "field_name": "work_email"}, "position": {"x": 100, "y": 200}},
                        {"id": "q-size", "type": "question", "data": {"label": "Team Size", "field_name": "team_size"}, "position": {"x": 100, "y": 300}},
                        {"id": "cond-1", "type": "condition", "data": {"label": "Qualify", "condition": "team_size > 50"}, "position": {"x": 100, "y": 400}},
                        {"id": "act-save", "type": "action", "data": {"label": "Save Lead", "action_type": "save_lead"}, "position": {"x": 250, "y": 500}},
                        {"id": "msg-demo", "type": "message", "data": {"label": "Book Demo", "message": "Awesome! I'll have our team reach out within 24hrs."}, "position": {"x": 250, "y": 600}},
                        {"id": "msg-self", "type": "message", "data": {"label": "Self-Serve", "message": "Great! Start with our free plan and upgrade anytime."}, "position": {"x": -50, "y": 500}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "tr-1", "target": "msg-1"},
                        {"id": "e2", "source": "msg-1", "target": "q-email"},
                        {"id": "e3", "source": "q-email", "target": "q-size"},
                        {"id": "e4", "source": "q-size", "target": "cond-1"},
                        {"id": "e5", "source": "cond-1", "target": "act-save", "label": "Qualified"},
                        {"id": "e6", "source": "act-save", "target": "msg-demo"},
                        {"id": "e7", "source": "cond-1", "target": "msg-self", "label": "Self-Serve"},
                    ],
                },
            ))

        if sarah and not db.query(BotFlow).filter(BotFlow.bot_id == sarah.id, BotFlow.name == "Support Triage").first():
            db.add(BotFlow(
                bot_id=sarah.id,
                name="Support Triage",
                description="Routes support requests by topic: billing, technical, or account",
                flow_data={
                    "nodes": [
                        {"id": "tr-1", "type": "trigger", "data": {"label": "Support Request"}, "position": {"x": 200, "y": 0}},
                        {"id": "cond-billing", "type": "condition", "data": {"label": "Billing?", "condition": "topic == 'billing'"}, "position": {"x": 200, "y": 100}},
                        {"id": "ai-billing", "type": "ai_response", "data": {"label": "Billing AI", "prompt": "Help with billing questions"}, "position": {"x": 400, "y": 200}},
                        {"id": "cond-tech", "type": "condition", "data": {"label": "Technical?", "condition": "topic == 'technical'"}, "position": {"x": 200, "y": 200}},
                        {"id": "ai-tech", "type": "ai_response", "data": {"label": "Tech AI", "prompt": "Provide technical troubleshooting"}, "position": {"x": 400, "y": 300}},
                        {"id": "msg-fallback", "type": "message", "data": {"label": "General", "message": "Let me connect you with our team."}, "position": {"x": 0, "y": 300}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "tr-1", "target": "cond-billing"},
                        {"id": "e2", "source": "cond-billing", "target": "ai-billing", "label": "Yes"},
                        {"id": "e3", "source": "cond-billing", "target": "cond-tech", "label": "No"},
                        {"id": "e4", "source": "cond-tech", "target": "ai-tech", "label": "Yes"},
                        {"id": "e5", "source": "cond-tech", "target": "msg-fallback", "label": "No"},
                    ],
                },
            ))

        if alex and not db.query(BotFlow).filter(BotFlow.bot_id == alex.id, BotFlow.name == "Architecture Review").first():
            db.add(BotFlow(
                bot_id=alex.id,
                name="Architecture Review",
                description="AI-driven architecture assessment and recommendations",
                flow_data={
                    "nodes": [
                        {"id": "tr-1", "type": "trigger", "data": {"label": "Start"}, "position": {"x": 100, "y": 0}},
                        {"id": "msg-1", "type": "message", "data": {"label": "Welcome", "message": "I'm ready to review. What system aspect?"}, "position": {"x": 100, "y": 100}},
                        {"id": "ai-1", "type": "ai_response", "data": {"label": "Analysis", "prompt": "Analyze architecture and provide recommendations"}, "position": {"x": 100, "y": 200}},
                        {"id": "msg-2", "type": "message", "data": {"label": "Next Steps", "message": "Shall I generate a detailed report?"}, "position": {"x": 100, "y": 300}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "tr-1", "target": "msg-1"},
                        {"id": "e2", "source": "msg-1", "target": "ai-1"},
                        {"id": "e3", "source": "ai-1", "target": "msg-2"},
                    ],
                },
            ))
        db.commit()

        # ── 5. Create Lead Forms ──
        print("  📝 Creating lead forms...")
        for bot in bot_objects:
            if bot.name in ["Growth Gary", "Demo Dan", "Pitch Pete"]:
                if not db.query(LeadFormDB).filter(LeadFormDB.bot_id == bot.id).first():
                    fields = [
                        {"id": "f1", "name": "full_name", "label": "Full Name", "type": "text", "required": True},
                        {"id": "f2", "name": "work_email", "label": "Work Email", "type": "email", "required": True},
                        {"id": "f3", "name": "company", "label": "Company", "type": "text", "required": True},
                        {"id": "f4", "name": "team_size", "label": "Team Size", "type": "text", "required": False},
                    ]
                    db.add(LeadFormDB(
                        tenant_id=bot.tenant_id,
                        bot_id=bot.id,
                        title="Scale Your Business" if bot.name == "Growth Gary" else "Get Started",
                        fields=json.dumps(fields),
                    ))
        db.commit()

        # ── 6. Create Conversations + Messages ──
        print("  💬 Creating conversations...")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(25):
            target_bot = random.choice(bot_objects)
            script = random.choice(CONVERSATION_SCRIPTS)
            status = random.choice(["resolved", "resolved", "open", "new", "pending"])
            priority = random.choice(["low", "medium", "medium", "high"])

            conv = ConversationDB(
                tenant_id=target_bot.tenant_id,
                bot_id=target_bot.id,
                status=status,
                priority=priority,
                created_at=now - timedelta(
                    days=random.randint(0, 14),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                ),
            )
            db.add(conv)
            db.flush()

            # Add realistic conversation messages
            for sender, text in script:
                db.add(MessageDB(
                    conversation_id=conv.id,
                    sender=sender,
                    text=text,
                    created_at=conv.created_at + timedelta(
                        minutes=random.randint(0, 5),
                        seconds=random.randint(0, 59),
                    ),
                ))
        db.commit()

        # ── 7. Create Leads ──
        print("  🎯 Creating leads...")
        sales_bots = [b for b in bot_objects if b.name in ["Growth Gary", "Demo Dan", "Pitch Pete"]]
        for persona in LEAD_PERSONAS:
            target_bot = random.choice(sales_bots) if sales_bots else random.choice(bot_objects)
            lead_data = {
                "full_name": persona["name"],
                "work_email": persona["email"],
                "company": persona["company"],
                "team_size": persona["size"],
            }
            db.add(LeadDB(
                tenant_id=target_bot.tenant_id,
                bot_id=target_bot.id,
                conversation_id=random.randint(1, 20),
                data=json.dumps(lead_data),
                country=random.choice(COUNTRIES),
                source=random.choice(SOURCES),
                created_at=now - timedelta(days=random.randint(0, 14)),
            ))
        db.commit()

        # ── Summary ──
        print("─" * 50)
        print(f"  ✅ Tenants:        {len(TENANTS)}")
        print(f"  ✅ Bot Personas:   {len(BOT_PERSONAS)}")
        print(f"  ✅ FAQs:           {sum(len(v) for v in FAQS.values())}")
        print(f"  ✅ Flows:          3")
        print(f"  ✅ Conversations:  25")
        print(f"  ✅ Leads:          {len(LEAD_PERSONAS)}")
        print("─" * 50)
        print("🚀 Seeding complete!")

    except Exception as e:
        db.rollback()
        print(f"❌ Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
