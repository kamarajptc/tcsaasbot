#!/usr/bin/env python3
"""
Seed synthetic customer conversations/messages/leads for Customers Real-Time report.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal, ConversationDB, MessageDB, LeadDB  # noqa: E402
from app.models.bot import Bot  # noqa: E402


CUSTOMER_PERSONAS = [
    {"name": "Ravi Kumar", "email": "ravi.kumar@example.com", "country": "IN", "source": "Website"},
    {"name": "Anita Sharma", "email": "anita.sharma@example.com", "country": "IN", "source": "Direct"},
    {"name": "John Miller", "email": "john.miller@example.com", "country": "US", "source": "Google"},
    {"name": "Sara Lee", "email": "sara.lee@example.com", "country": "UK", "source": "LinkedIn"},
    {"name": "Mohan Raj", "email": "mohan.raj@example.com", "country": "IN", "source": "Referral"},
    {"name": "Priya Nair", "email": "priya.nair@example.com", "country": "IN", "source": "Website"},
]

USER_QUESTIONS = [
    "Can you explain your pricing plans?",
    "Do you support integrations and APIs?",
    "How quickly can we get started?",
    "Can I talk to a human agent?",
    "What are your key product features?",
    "Do you have enterprise support?",
]

BOT_ANSWERS = [
    "We support onboarding, setup guidance, and product-specific workflows.",
    "Yes, we provide API and integration support with secure tenant isolation.",
    "Most teams can onboard within a few days depending on scope.",
    "I can route this to a human specialist if needed.",
    "Core features include chatbot automation, analytics, and secure multitenant controls.",
    "Enterprise plans include advanced support and governance controls.",
]


def main() -> int:
    random.seed(42)
    db = SessionLocal()
    try:
        bots = db.query(Bot).order_by(Bot.id.asc()).all()
        if not bots:
            print("No bots found. Seed tenants/bots first.")
            return 1

        # Clean only customer interaction tables before reseed.
        db.query(MessageDB).delete(synchronize_session=False)
        db.query(LeadDB).delete(synchronize_session=False)
        db.query(ConversationDB).delete(synchronize_session=False)
        db.commit()

        now = datetime.utcnow()
        statuses = ["new", "open", "pending", "resolved"]

        total_conversations = 0
        total_messages = 0
        total_leads = 0

        for bot in bots:
            # 6 synthetic conversations per bot => with 5 bots gives 30 rows
            for idx in range(6):
                persona = CUSTOMER_PERSONAS[(bot.id + idx) % len(CUSTOMER_PERSONAS)]
                status = statuses[idx % len(statuses)]
                created_at = now - timedelta(minutes=(bot.id * 31 + idx * 11))
                agent_requested = status == "pending" or (idx % 5 == 0)

                conv = ConversationDB(
                    tenant_id=bot.tenant_id,
                    bot_id=bot.id,
                    status=status,
                    priority="high" if idx % 4 == 0 else "medium",
                    agent_requested=agent_requested,
                    created_at=created_at,
                )
                db.add(conv)
                db.flush()
                total_conversations += 1

                # message timeline
                user_text = USER_QUESTIONS[idx % len(USER_QUESTIONS)]
                bot_text = BOT_ANSWERS[idx % len(BOT_ANSWERS)]
                msg1 = MessageDB(
                    conversation_id=conv.id,
                    sender="user",
                    text=user_text,
                    created_at=created_at + timedelta(seconds=20),
                )
                msg2 = MessageDB(
                    conversation_id=conv.id,
                    sender="bot" if not agent_requested else "agent",
                    agent_id=("agent-ops-01" if agent_requested else None),
                    text=bot_text,
                    created_at=created_at + timedelta(seconds=50),
                )
                db.add(msg1)
                db.add(msg2)
                total_messages += 2

                # Add a lead for half the conversations
                if idx % 2 == 0:
                    lead = LeadDB(
                        tenant_id=bot.tenant_id,
                        bot_id=bot.id,
                        conversation_id=conv.id,
                        data=json.dumps(
                            {
                                "name": persona["name"],
                                "email": persona["email"],
                                "company": f"{bot.name} Prospect",
                                "intent": "demo_request" if idx % 3 == 0 else "pricing",
                            }
                        ),
                        country=persona["country"],
                        source=persona["source"],
                        created_at=created_at + timedelta(seconds=70),
                    )
                    db.add(lead)
                    total_leads += 1

        db.commit()
        print(f"Seeded conversations={total_conversations}, messages={total_messages}, leads={total_leads}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

