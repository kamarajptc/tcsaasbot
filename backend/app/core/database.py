from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, text, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

from app.core.config import get_settings

settings = get_settings()

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

connect_args = {}
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class DocumentDB(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content_snippet = Column(String)
    source = Column(String)
    tenant_id = Column(String, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class ConversationDB(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    bot_id = Column(Integer, index=True, nullable=True) # Optional for now
    status = Column(String, default="new") # new, open, pending, resolved
    priority = Column(String, default="medium") # low, medium, high
    agent_requested = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    messages = relationship("MessageDB", back_populates="conversation")

class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=True) # Will be made mandatory in next phase
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    sender = Column(String) # 'user' or 'bot'
    agent_id = Column(String, index=True, nullable=True)  # set when sender='agent'
    text = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    conversation = relationship("ConversationDB", back_populates="messages")

class TenantDB(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    plan = Column(String, default="starter") # starter, pro, enterprise
    is_active = Column(Boolean, default=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class TenantUsageDB(Base):
    __tablename__ = "tenant_usage"
    tenant_id = Column(String, primary_key=True, index=True)
    messages_sent = Column(Integer, default=0)
    documents_indexed = Column(Integer, default=0)
    last_reset = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class RateLimitPolicyDB(Base):
    __tablename__ = "rate_limit_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "route_key", name="uq_rate_limit_policy_tenant_route"),
        UniqueConstraint("plan", "route_key", name="uq_rate_limit_policy_plan_route"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=True)
    plan = Column(String, index=True, nullable=True)
    route_key = Column(String, index=True, nullable=False)
    rpm_limit = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class RateLimitEventDB(Base):
    __tablename__ = "rate_limit_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=True)
    plan = Column(String, index=True, nullable=True)
    route_key = Column(String, index=True, nullable=False)
    request_path = Column(String, nullable=False)
    limiter_key = Column(String, nullable=False)
    limit_value = Column(Integer, nullable=False)
    retry_after_seconds = Column(Integer, default=0)
    exceeded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)


class TenantAlertSettingsDB(Base):
    __tablename__ = "tenant_alert_settings"

    tenant_id = Column(String, primary_key=True, index=True)
    rate_limit_email_enabled = Column(Boolean, default=False)
    rate_limit_email_recipient = Column(String, nullable=True)
    rate_limit_webhook_enabled = Column(Boolean, default=False)
    rate_limit_webhook_url = Column(String, nullable=True)
    rate_limit_min_hits = Column(Integer, default=5)
    rate_limit_window_minutes = Column(Integer, default=60)
    rate_limit_cooldown_minutes = Column(Integer, default=60)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class RateLimitAlertDeliveryDB(Base):
    __tablename__ = "rate_limit_alert_deliveries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "route_key", "channel", name="uq_rate_limit_alert_delivery_route_channel"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    route_key = Column(String, index=True, nullable=False)
    channel = Column(String, index=True, nullable=False)  # email | webhook
    hits = Column(Integer, nullable=False, default=0)
    last_sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AdminAuditLogDB(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    actor_tenant_id = Column(String, index=True, nullable=False)
    actor_role = Column(String, nullable=False, default="admin")
    action = Column(String, index=True, nullable=False)
    target_type = Column(String, index=True, nullable=False)
    target_id = Column(String, nullable=True)
    metadata_json = Column(String, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)

class LeadFormDB(Base):
    __tablename__ = "lead_forms"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    title = Column(String, default="Contact Us")
    fields = Column(String)  # JSON string of field definitions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class LeadDB(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    bot_id = Column(Integer, index=True)
    conversation_id = Column(Integer, index=True)
    data = Column(String)  # JSON string of submitted data
    country = Column(String, nullable=True)
    source = Column(String, default="Direct") # e.g. "Google", "Widget", "Direct"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class EmailSettingsDB(Base):
    __tablename__ = "email_settings"
    tenant_id = Column(String, primary_key=True, index=True)
    smtp_host = Column(String)
    smtp_port = Column(Integer)
    smtp_user = Column(String)
    smtp_pass = Column(String)
    sender_email = Column(String)
    is_enabled = Column(Boolean, default=False)


class PlanLimitsDB(Base):
    __tablename__ = "plan_limits"

    plan = Column(String, primary_key=True, index=True) # starter, pro, enterprise
    message_limit = Column(Integer, nullable=False)
    document_limit = Column(Integer, nullable=False)
    bot_limit = Column(Integer, nullable=False) # Number of bots allowed
    throttling_rpm = Column(Integer, default=60) # Default RPM
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class StripeEventDB(Base):
    __tablename__ = "stripe_events"
    event_id = Column(String, primary_key=True, index=True)
    event_type = Column(String, index=True)
    tenant_id = Column(String, index=True, nullable=True)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AgentTransferRuleDB(Base):
    __tablename__ = "agent_transfer_rules"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    rule_type = Column(String, nullable=False)  # keyword | time | manual
    condition = Column(String, nullable=False)
    action = Column(String, default="transfer")  # transfer | notify
    transfer_message = Column(String, nullable=True)
    notify_email = Column(String, nullable=True)
    notify_webhook = Column(String, nullable=True)
    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AnalyticsSnapshotScheduleDB(Base):
    __tablename__ = "analytics_snapshot_schedules"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    frequency = Column(String, nullable=False)  # daily | weekly
    timezone = Column(String, default="UTC")
    report_type = Column(String, default="overview")
    recipient_email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AnalyticsExportJobDB(Base):
    __tablename__ = "analytics_export_jobs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    requested_by = Column(String, nullable=False)
    report_type = Column(String, nullable=False)
    filters_json = Column(String, default="{}")
    status = Column(String, default="queued")  # queued | processing | completed | failed
    artifact_csv = Column(String, nullable=True)  # inline CSV artifact for MVP
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    completed_at = Column(DateTime, nullable=True)

def init_db():
    import logging
    db_logger = logging.getLogger("TangentCloud")
    # Import all models here to ensure they are registered with Base metadata
    from app.models.bot import Bot
    Base.metadata.create_all(bind=engine)
    # Lightweight runtime migration for legacy databases.
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN response_mode VARCHAR(40) DEFAULT 'knowledge_plus_reasoning'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN welcome_message VARCHAR(255) DEFAULT 'Welcome to TangentCloud. Ask me anything.'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN primary_color VARCHAR(20) DEFAULT '#2563eb'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN avatar_url VARCHAR(255)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN position VARCHAR(20) DEFAULT 'right'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN placeholder_text VARCHAR(100) DEFAULT 'Type a message...'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN bubble_greeting VARCHAR(100)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN tools JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN flow_data JSONB DEFAULT '{}'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN enabled_flows JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN rich_messages_enabled BOOLEAN DEFAULT true"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN quick_replies JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN canned_responses JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN greeting_enabled BOOLEAN DEFAULT true"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN greeting_message VARCHAR(500)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN faq_enabled BOOLEAN DEFAULT true"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN custom_answers JSONB DEFAULT '{}'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN agent_transfer_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN agent_email VARCHAR(255)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN agent_webhook VARCHAR(500)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN transfer_trigger_keywords JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN small_talk_enabled BOOLEAN DEFAULT true"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN small_talk_responses JSONB DEFAULT '{}'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN collect_name BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN collect_email BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN collect_phone BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN collect_custom_fields JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN shopify_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN shopify_store_url VARCHAR(255)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN slack_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN slack_webhook VARCHAR(500)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN zendesk_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN zendesk_subdomain VARCHAR(100)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN freshdesk_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN freshdesk_domain VARCHAR(100)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN goals JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN tags JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN ab_test_enabled BOOLEAN DEFAULT false"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN ab_test_variants JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN flow_version INTEGER DEFAULT 1"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN flow_version_history JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bots ADD COLUMN allowed_domains JSONB DEFAULT '[]'"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE messages ADD COLUMN agent_id VARCHAR(255)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE bot_faqs ADD COLUMN tenant_id VARCHAR(50)"))
            conn.execute(text("ALTER TABLE bot_flows ADD COLUMN tenant_id VARCHAR(50)"))
            conn.execute(text("ALTER TABLE bot_integrations ADD COLUMN tenant_id VARCHAR(50)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_faqs_tenant_id ON bot_faqs (tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_flows_tenant_id ON bot_flows (tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_integrations_tenant_id ON bot_integrations (tenant_id)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE messages ADD COLUMN tenant_id VARCHAR(50)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_tenant_id ON messages (tenant_id)"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_rate_limit_policy_tenant_route_idx ON rate_limit_policies (tenant_id, route_key) WHERE tenant_id IS NOT NULL"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_rate_limit_policy_plan_route_idx ON rate_limit_policies (plan, route_key) WHERE plan IS NOT NULL"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_rate_limit_alert_delivery_route_channel_idx ON rate_limit_alert_deliveries (tenant_id, route_key, channel)"))
        except Exception:
            pass
    defaults = [
        ("starter", "default", 60),
        ("starter", "chat", 30),
        ("starter", "chat_public", 20),
        ("starter", "dashboard_conversations", 60),
        ("starter", "ingest_scrape", 3),
        ("starter", "auth", 10),
        ("pro", "default", 180),
        ("pro", "chat", 90),
        ("pro", "chat_public", 45),
        ("pro", "dashboard_conversations", 180),
        ("pro", "ingest_scrape", 8),
        ("pro", "auth", 20),
        ("enterprise", "default", 600),
        ("enterprise", "chat", 240),
        ("enterprise", "chat_public", 120),
        ("enterprise", "dashboard_conversations", 600),
        ("enterprise", "ingest_scrape", 20),
        ("enterprise", "auth", 60),
    ]

    plan_defaults = [
        ("starter", 100, 5, 1, 60),
        ("pro", 5000, 50, 10, 180),
        ("enterprise", 100000, 1000, 999, 600),
    ]
    session = SessionLocal()
    try:
        existing = session.query(RateLimitPolicyDB).count()
        if existing == 0:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for plan, route_key, rpm_limit in defaults:
                session.add(
                    RateLimitPolicyDB(
                        tenant_id=None,
                        plan=plan,
                        route_key=route_key,
                        rpm_limit=rpm_limit,
                        is_active=True,
                        created_at=now,
                    )
                )
        
        existing_plans = session.query(PlanLimitsDB).count()
        if existing_plans == 0:
            for plan, msg_limit, doc_limit, bot_limit, rpm_limit in plan_defaults:
                session.add(
                    PlanLimitsDB(
                        plan=plan,
                        message_limit=msg_limit,
                        document_limit=doc_limit,
                        bot_limit=bot_limit,
                        throttling_rpm=rpm_limit
                    )
                )
        session.commit()
    except Exception as e:
        session.rollback()
        db_logger.error(f"database_init_failed: {str(e)}")
    finally:
        session.close()
    db_logger.info("database_initialized", extra={
        "database_url": SQLALCHEMY_DATABASE_URL.split("///")[-1],
        "tables": list(Base.metadata.tables.keys())
    })

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
