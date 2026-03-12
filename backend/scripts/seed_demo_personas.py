from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import (  # noqa: E402
    SessionLocal,
    TenantDB,
    TenantUsageDB,
    ConversationDB,
    MessageDB,
    LeadDB,
)
from app.models.bot import Bot  # noqa: E402


NOW = datetime.now(timezone.utc).replace(tzinfo=None)

DEMO_TENANTS = [
    {
        "id": "ops@tangentcloud.in",
        "name": "TangentCloud",
        "plan": "enterprise",
        "usage": {"messages_sent": 28, "documents_indexed": 7},
        "bot": {
            "name": "TangentCloud Assistant",
            "description": "AI SaaS Platforms assistant for TangentCloud",
            "prompt_template": (
                "You are TangentCloud Assistant. Provide clear and concise responses "
                "for TangentCloud in the category AI SaaS Platforms."
            ),
            "welcome_message": "Welcome to TangentCloud. Ask me anything.",
        },
        "conversations": [
            {
                "status": "new",
                "priority": "high",
                "agent_requested": True,
                "minutes_ago": 14,
                "source": "Direct",
                "country": "IN",
                "lead": {
                    "name": "Anita Sharma",
                    "email": "anita.sharma@example.com",
                    "company": "TangentCloud Assistant Prospect",
                    "intent": "demo_request",
                },
                "messages": [
                    ("user", None, "Can you explain your pricing plans?"),
                    ("agent", "agent-ops-01", "We support onboarding, setup guidance, and product-specific workflows."),
                ],
            },
            {
                "status": "open",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 30,
                "source": "Website",
                "country": None,
                "lead": None,
                "messages": [
                    ("user", None, "Do you support integrations and APIs?"),
                    ("bot", None, "Yes, we provide API and integration support with secure tenant isolation."),
                ],
            },
            {
                "status": "pending",
                "priority": "medium",
                "agent_requested": True,
                "minutes_ago": 47,
                "source": "LinkedIn",
                "country": "UK",
                "lead": {
                    "name": "Sara Lee",
                    "email": "sara.lee@example.com",
                    "company": "TangentCloud Assistant Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "How quickly can we get started?"),
                    ("agent", "agent-ops-01", "Most teams can onboard within a few days depending on scope."),
                ],
            },
        ],
    },
    {
        "id": "ops@dataflo.io",
        "name": "dataflo",
        "plan": "pro",
        "usage": {"messages_sent": 18, "documents_indexed": 15},
        "bot": {
            "name": "Dataflo Workflow Guide",
            "description": "No-Code Data Automation assistant for dataflo",
            "prompt_template": (
                "You are Dataflo Workflow Guide. Provide clear and concise responses "
                "for dataflo in the category No-Code Data Automation."
            ),
            "welcome_message": "Welcome to dataflo. Ask me anything.",
        },
        "conversations": [
            {
                "status": "new",
                "priority": "high",
                "agent_requested": True,
                "minutes_ago": 18,
                "source": "LinkedIn",
                "country": "UK",
                "lead": {
                    "name": "Sara Lee",
                    "email": "sara.lee@example.com",
                    "company": "Dataflo Workflow Guide Prospect",
                    "intent": "demo_request",
                },
                "messages": [
                    ("user", None, "Can you explain your pricing plans?"),
                    ("agent", "agent-ops-01", "We support onboarding, setup guidance, and product-specific workflows."),
                ],
            },
            {
                "status": "open",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 36,
                "source": "Website",
                "country": "IN",
                "lead": {
                    "name": "Priya Nair",
                    "email": "priya.nair@example.com",
                    "company": "Dataflo Workflow Guide Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "Do you support integrations and APIs?"),
                    ("bot", None, "Yes, we provide API and integration support with secure tenant isolation."),
                ],
            },
            {
                "status": "resolved",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 61,
                "source": "Direct",
                "country": "IN",
                "lead": None,
                "messages": [
                    ("user", None, "What are your key product features?"),
                    ("bot", None, "Core features include chatbot automation, analytics, and secure multitenant controls."),
                ],
            },
        ],
    },
    {
        "id": "ops@adamsbridge.com",
        "name": "Adamsbridge",
        "plan": "enterprise",
        "usage": {"messages_sent": 21, "documents_indexed": 10},
        "bot": {
            "name": "Adamsbridge IAM Assistant",
            "description": "Identity and Access Management assistant for Adamsbridge",
            "prompt_template": (
                "You are Adamsbridge IAM Assistant. Provide clear and concise responses "
                "for Adamsbridge in the category Identity and Access Management."
            ),
            "welcome_message": "Welcome to Adamsbridge. Ask me anything.",
        },
        "conversations": [
            {
                "status": "new",
                "priority": "high",
                "agent_requested": True,
                "minutes_ago": 12,
                "source": "Referral",
                "country": "IN",
                "lead": {
                    "name": "Mohan Raj",
                    "email": "mohan.raj@example.com",
                    "company": "Adamsbridge IAM Assistant Prospect",
                    "intent": "demo_request",
                },
                "messages": [
                    ("user", None, "Can you explain your pricing plans?"),
                    ("agent", "agent-ops-01", "We support onboarding, setup guidance, and product-specific workflows."),
                ],
            },
            {
                "status": "pending",
                "priority": "medium",
                "agent_requested": True,
                "minutes_ago": 33,
                "source": "Website",
                "country": "IN",
                "lead": {
                    "name": "Ravi Kumar",
                    "email": "ravi.kumar@example.com",
                    "company": "Adamsbridge IAM Assistant Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "Can I talk to a human agent?"),
                    ("bot", None, "I can route this to a human specialist if needed."),
                ],
            },
            {
                "status": "resolved",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 75,
                "source": "Google",
                "country": "US",
                "lead": {
                    "name": "John Miller",
                    "email": "john.miller@example.com",
                    "company": "Adamsbridge IAM Assistant Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "Do you have enterprise support?"),
                    ("agent", "agent-ops-01", "Enterprise plans include advanced support and governance controls."),
                ],
            },
        ],
    },
    {
        "id": "ops@workez.in",
        "name": "WorkEZ",
        "plan": "pro",
        "usage": {"messages_sent": 16, "documents_indexed": 10},
        "bot": {
            "name": "WorkEZ HR Assistant",
            "description": "HRMS and Payroll assistant for WorkEZ",
            "prompt_template": (
                "You are WorkEZ HR Assistant. Provide clear and concise responses "
                "for WorkEZ in the category HRMS and Payroll."
            ),
            "welcome_message": "Welcome to WorkEZ. Ask me anything.",
        },
        "conversations": [
            {
                "status": "new",
                "priority": "high",
                "agent_requested": True,
                "minutes_ago": 16,
                "source": "Website",
                "country": "IN",
                "lead": {
                    "name": "Priya Nair",
                    "email": "priya.nair@example.com",
                    "company": "WorkEZ HR Assistant Prospect",
                    "intent": "demo_request",
                },
                "messages": [
                    ("user", None, "Can you explain your pricing plans?"),
                    ("agent", "agent-ops-01", "We support onboarding, setup guidance, and product-specific workflows."),
                ],
            },
            {
                "status": "open",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 43,
                "source": "Direct",
                "country": "IN",
                "lead": {
                    "name": "Anita Sharma",
                    "email": "anita.sharma@example.com",
                    "company": "WorkEZ HR Assistant Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "How quickly can we get started?"),
                    ("bot", None, "Most teams can onboard within a few days depending on scope."),
                ],
            },
            {
                "status": "resolved",
                "priority": "medium",
                "agent_requested": False,
                "minutes_ago": 82,
                "source": "LinkedIn",
                "country": "UK",
                "lead": {
                    "name": "Sara Lee",
                    "email": "sara.lee@example.com",
                    "company": "WorkEZ HR Assistant Prospect",
                    "intent": "pricing",
                },
                "messages": [
                    ("user", None, "What are your key product features?"),
                    ("bot", None, "Core features include chatbot automation, analytics, and secure multitenant controls."),
                ],
            },
        ],
    },
]


def upsert_tenant(session, tenant_data: dict) -> str:
    tenant = session.get(TenantDB, tenant_data["id"])
    if tenant is None:
        session.add(
            TenantDB(
                id=tenant_data["id"],
                name=tenant_data["name"],
                plan=tenant_data["plan"],
                is_active=True,
                created_at=NOW,
            )
        )
        return "created"
    tenant.name = tenant_data["name"]
    tenant.plan = tenant_data["plan"]
    tenant.is_active = True
    return "updated"


def upsert_usage(session, tenant_id: str, usage_data: dict) -> str:
    usage = session.get(TenantUsageDB, tenant_id)
    if usage is None:
        session.add(
            TenantUsageDB(
                tenant_id=tenant_id,
                messages_sent=usage_data["messages_sent"],
                documents_indexed=usage_data["documents_indexed"],
                last_reset=NOW,
            )
        )
        return "created"
    usage.messages_sent = usage_data["messages_sent"]
    usage.documents_indexed = usage_data["documents_indexed"]
    usage.last_reset = NOW
    return "updated"


def remove_perf_bots(session, tenant_id: str) -> int:
    perf_bots = (
        session.query(Bot)
        .filter(Bot.tenant_id == tenant_id, Bot.name.like("Perf Bot %"))
        .all()
    )
    removed = len(perf_bots)
    for bot in perf_bots:
        session.delete(bot)
    return removed


def upsert_bot(session, tenant_id: str, bot_data: dict) -> Bot:
    bot = (
        session.query(Bot)
        .filter(Bot.tenant_id == tenant_id, Bot.name == bot_data["name"])
        .one_or_none()
    )
    if bot is None:
        bot = Bot(
            tenant_id=tenant_id,
            name=bot_data["name"],
            description=bot_data["description"],
            prompt_template=bot_data["prompt_template"],
            response_mode="knowledge_plus_reasoning",
            welcome_message=bot_data["welcome_message"],
            primary_color="#2563eb",
            position="right",
            placeholder_text="Type a message...",
            is_active=True,
            tools=[],
            flow_data={},
            enabled_flows=[],
            rich_messages_enabled=True,
            quick_replies=[],
            canned_responses=[],
            greeting_enabled=True,
            greeting_message=None,
            faq_enabled=True,
            custom_answers={},
            agent_transfer_enabled=False,
            agent_email=None,
            agent_webhook=None,
            transfer_trigger_keywords=[],
            small_talk_enabled=True,
            small_talk_responses=[],
            collect_name=False,
            collect_email=False,
            collect_phone=False,
            collect_custom_fields=[],
            shopify_enabled=False,
            shopify_store_url=None,
            slack_enabled=False,
            slack_webhook=None,
            zendesk_enabled=False,
            zendesk_subdomain=None,
            freshdesk_enabled=False,
            freshdesk_domain=None,
            goals=[],
            tags=[],
            ab_test_enabled=False,
            ab_test_variants=[],
            flow_version=1,
            flow_version_history=[],
            created_at=NOW,
        )
        session.add(bot)
        session.flush()
        return bot

    bot.description = bot_data["description"]
    bot.prompt_template = bot_data["prompt_template"]
    bot.response_mode = "knowledge_plus_reasoning"
    bot.welcome_message = bot_data["welcome_message"]
    bot.primary_color = "#2563eb"
    bot.position = "right"
    bot.placeholder_text = "Type a message..."
    bot.is_active = True
    bot.faq_enabled = True
    bot.greeting_enabled = True
    bot.rich_messages_enabled = True
    bot.small_talk_enabled = True
    return bot


def clear_workspace_for_tenant(session, tenant_id: str) -> None:
    conversation_ids = [
        row[0]
        for row in session.query(ConversationDB.id)
        .filter(ConversationDB.tenant_id == tenant_id)
        .all()
    ]
    if conversation_ids:
        session.query(MessageDB).filter(
            MessageDB.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
        session.query(LeadDB).filter(
            LeadDB.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    session.query(ConversationDB).filter(
        ConversationDB.tenant_id == tenant_id
    ).delete(synchronize_session=False)


def seed_conversations(session, tenant_data: dict, bot_id: int) -> tuple[int, int, int]:
    clear_workspace_for_tenant(session, tenant_data["id"])
    conversation_count = 0
    message_count = 0
    lead_count = 0

    for convo_index, convo in enumerate(tenant_data["conversations"], start=1):
        created_at = NOW - timedelta(minutes=convo["minutes_ago"])
        conversation = ConversationDB(
            tenant_id=tenant_data["id"],
            bot_id=bot_id,
            status=convo["status"],
            priority=convo["priority"],
            agent_requested=convo["agent_requested"],
            created_at=created_at,
        )
        session.add(conversation)
        session.flush()
        conversation_count += 1

        for msg_index, (sender, agent_id, text) in enumerate(convo["messages"], start=1):
            session.add(
                MessageDB(
                    conversation_id=conversation.id,
                    sender=sender,
                    agent_id=agent_id,
                    text=text,
                    created_at=created_at + timedelta(seconds=msg_index * 30),
                )
            )
            message_count += 1

        if convo["lead"]:
            session.add(
                LeadDB(
                    tenant_id=tenant_data["id"],
                    bot_id=bot_id,
                    conversation_id=conversation.id,
                    data=json.dumps(convo["lead"]),
                    country=convo["country"],
                    source=convo["source"],
                    created_at=created_at + timedelta(minutes=1),
                )
            )
            lead_count += 1

    return conversation_count, message_count, lead_count


def main() -> None:
    session = SessionLocal()
    try:
        results: list[str] = []
        total_conversations = 0
        total_messages = 0
        total_leads = 0

        for tenant_data in DEMO_TENANTS:
            tenant_status = upsert_tenant(session, tenant_data)
            usage_status = upsert_usage(session, tenant_data["id"], tenant_data["usage"])
            removed_perf_bots = remove_perf_bots(session, tenant_data["id"])
            bot = upsert_bot(session, tenant_data["id"], tenant_data["bot"])
            session.flush()
            convs, msgs, leads = seed_conversations(session, tenant_data, bot.id)
            total_conversations += convs
            total_messages += msgs
            total_leads += leads
            results.append(
                f"{tenant_data['id']}: tenant={tenant_status}, usage={usage_status}, "
                f"removed_perf_bots={removed_perf_bots}, bot={bot.name}, "
                f"conversations={convs}, messages={msgs}, leads={leads}"
            )

        session.commit()
        print("Demo persona seed complete.")
        print("Demo login password: password123")
        print(
            f"Seeded totals: conversations={total_conversations}, "
            f"messages={total_messages}, leads={total_leads}"
        )
        for line in results:
            print(line)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
